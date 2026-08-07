# -*- coding: utf-8 -*-
"""Thin synchronous HTTP client over ``requests``.

Handles JSON POST, Server-Sent-Events streaming, timeouts, proxy normalization
and a small retry on 429 / 5xx. Kept deliberately minimal — the agent runtime's
retry/interrupt machinery is out of scope for the Odoo port.
"""
from __future__ import annotations

import contextlib
import json
import logging
import threading
import time

from .utils import normalize_proxy_url

_logger = logging.getLogger(__name__)

# Per-thread outbound policy (set by the model layer from config before each
# operation). Defaults are safe: metadata/link-local are always blocked by the
# guard regardless; these toggle the *optional* extra restrictions.
_policy = threading.local()


def set_outbound_policy(*, block_private=False, allowlist=None):
    """Configure the SSRF guard for the current thread (called per request)."""
    _policy.block_private = bool(block_private)
    _policy.allowlist = list(allowlist) if allowlist else None


def _get_policy():
    return (getattr(_policy, 'block_private', False),
            getattr(_policy, 'allowlist', None))

try:
    import requests
except ImportError:  # pragma: no cover - requests ships with Odoo
    requests = None

# Optional TLS-fingerprint impersonation (curl_cffi) — used for Anthropic's
# Cloudflare-fronted endpoints so OAuth (claude.ai) traffic presents a real
# browser/Claude-Code ClientHello instead of python-requests' fingerprint.
# When absent, callers fall back to plain requests (works unless Cloudflare
# challenges the server IP).
try:
    from curl_cffi import requests as _curl_requests  # type: ignore
    IMPERSONATE_AVAILABLE = True
except Exception:  # noqa: BLE001 - any import/runtime issue disables impersonation
    _curl_requests = None
    IMPERSONATE_AVAILABLE = False


class AiHttpError(Exception):
    """Raised when an upstream provider returns a non-2xx response."""

    def __init__(self, status_code, message, body=None):
        self.status_code = status_code
        self.body = body
        super().__init__(message)


def _require_requests():
    if requests is None:
        raise AiHttpError(0, "The 'requests' Python package is required.")


def _proxies(proxy_url):
    url = normalize_proxy_url(proxy_url)
    if not url:
        return None
    return {'http': url, 'https': url}


@contextlib.contextmanager
def _guarded(url, proxy_url=None):
    """SSRF gate around a request: validate the target/proxy, then PIN DNS to the
    vetted IP for the connect so resolve-time and connect-time can't diverge
    (DNS rebinding). Pins are thread-local and cleared on exit.
    """
    from . import url_guard, dns_pin
    block_private, allowlist = _get_policy()
    url_guard.validate_outbound_url(url, block_private=block_private, allowlist=allowlist)
    pinned = False
    try:
        # Pin the target host. Direct calls connect here; SOCKS5/SOCKS4 proxies
        # resolve the target client-side too, so pinning it closes rebinding on
        # that path as well (a no-op for HTTP/remote-DNS proxies that resolve
        # server-side — documented residual).
        thost, tport = url_guard.host_port(url)
        tip = url_guard.safe_resolve(thost, tport, block_private=block_private)
        if tip:
            dns_pin.set_pin(thost, tip)
            pinned = True
        if proxy_url:
            # urllib3 connects to the PROXY first — vet + pin its host too.
            phost, pport = url_guard.validate_proxy_url(proxy_url, block_private=block_private)
            pip = url_guard.safe_resolve(phost, pport, block_private=block_private)
            if pip:
                dns_pin.set_pin(phost, pip)
                pinned = True
        yield
    finally:
        if pinned:
            dns_pin.clear_pins()


def _curl_guard(url, proxy_url=None):
    """SSRF vet for the curl_cffi (libcurl) path.

    dns_pin monkeypatches Python's socket.getaddrinfo, which libcurl does NOT
    use — so the connect-time pin doesn't apply here. We still run the full
    static guard (scheme/allowlist/metadata/literal-IP) and safe_resolve, which
    REJECTS any host that resolves to a blocked address. This path is only used
    for fixed, trusted Anthropic hosts (not attacker-controlled DNS), so the
    residual rebinding window safe_resolve leaves open is not reachable here.
    """
    from . import url_guard
    block_private, allowlist = _get_policy()
    url_guard.validate_outbound_url(url, block_private=block_private, allowlist=allowlist)
    thost, tport = url_guard.host_port(url)
    url_guard.safe_resolve(thost, tport, block_private=block_private)
    if proxy_url:
        phost, pport = url_guard.validate_proxy_url(proxy_url, block_private=block_private)
        url_guard.safe_resolve(phost, pport, block_private=block_private)


def _curl_post(url, *, headers=None, json_body=None, timeout=120.0, proxy_url=None,
               impersonate='chrome', stream=False):
    """POST via curl_cffi with a browser TLS fingerprint. Returns the response."""
    _curl_guard(url, proxy_url)
    return _curl_requests.post(
        url, headers=headers or {}, json=json_body, timeout=timeout,
        impersonate=impersonate, allow_redirects=False,
        proxies=_proxies(proxy_url), stream=stream)


def _curl_get(url, *, headers=None, timeout=30.0, proxy_url=None, impersonate='chrome'):
    """GET via curl_cffi with a browser TLS fingerprint. Returns the response."""
    _curl_guard(url, proxy_url)
    return _curl_requests.get(
        url, headers=headers or {}, timeout=timeout, impersonate=impersonate,
        allow_redirects=False, proxies=_proxies(proxy_url))


def _curl_post_sse(url, *, headers=None, json_body=None, timeout=600.0,
                   proxy_url=None, impersonate='chrome'):
    """Streaming SSE over curl_cffi (browser TLS fingerprint). Yields parsed events."""
    resp = _curl_post(url, headers=headers, json_body=json_body, timeout=timeout,
                      proxy_url=proxy_url, impersonate=impersonate, stream=True)
    try:
        _raise_for_status(resp)
        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            if isinstance(raw_line, bytes):
                raw_line = raw_line.decode('utf-8', 'replace')
            line = raw_line.strip()
            if not line.startswith('data:'):
                continue
            payload = line[len('data:'):].strip()
            if payload == '[DONE]':
                break
            try:
                yield json.loads(payload)
            except (ValueError, TypeError):
                _logger.debug("Skipping non-JSON SSE line: %s", payload[:120])
                continue
    finally:
        try:
            resp.close()
        except Exception:  # noqa: BLE001
            pass


def _raise_for_status(resp):
    if resp.status_code >= 400:
        try:
            body = resp.json()
        except (ValueError, AttributeError):
            body = resp.text
        msg = None
        if isinstance(body, dict):
            err = body.get('error')
            if isinstance(err, dict):
                msg = err.get('message')
            elif isinstance(err, str):
                # OAuth-style flat error: {"error": "...", "error_description": "..."}
                # (e.g. Anthropic's token endpoint) — surface the human-readable part.
                msg = body.get('error_description') or err
        raise AiHttpError(
            resp.status_code,
            msg or f"HTTP {resp.status_code}: {str(body)[:500]}",
            body=body,
        )


def post_json(url, *, headers=None, json_body=None, timeout=120.0,
              proxy_url=None, max_retries=2, impersonate=None):
    """POST JSON and return the parsed JSON response.

    Retries once or twice on 429 / 5xx with a short backoff. When *impersonate*
    is set (e.g. 'chrome') and curl_cffi is available, the request is sent with
    a browser TLS fingerprint (Anthropic/Cloudflare); otherwise plain requests.
    """
    use_curl = bool(impersonate) and IMPERSONATE_AVAILABLE
    if not use_curl:
        _require_requests()
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            if use_curl:
                resp = _curl_post(url, headers=headers, json_body=json_body,
                                  timeout=timeout, proxy_url=proxy_url, impersonate=impersonate)
            else:
                with _guarded(url, proxy_url):
                    resp = requests.post(
                        url, headers=headers or {}, json=json_body,
                        timeout=timeout, proxies=_proxies(proxy_url), allow_redirects=False,
                    )
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                time.sleep(0.6 * (attempt + 1))
                continue
            _raise_for_status(resp)
            return resp.json()
        except AiHttpError:
            raise
        except Exception as exc:  # network / timeout
            last_exc = exc
            if attempt < max_retries:
                time.sleep(0.6 * (attempt + 1))
                continue
            raise AiHttpError(0, f"Request to {url} failed: {exc}") from exc
    if last_exc:
        raise AiHttpError(0, f"Request to {url} failed: {last_exc}")


def get_json(url, *, headers=None, timeout=30.0, proxy_url=None, impersonate=None):
    """GET JSON and return the parsed response.

    When *impersonate* is set and curl_cffi is available, the request uses a
    browser TLS fingerprint (for Cloudflare-fronted hosts like Anthropic's
    ``/v1/models``); otherwise plain requests.
    """
    if impersonate and IMPERSONATE_AVAILABLE:
        resp = _curl_get(url, headers=headers, timeout=timeout,
                         proxy_url=proxy_url, impersonate=impersonate)
        _raise_for_status(resp)
        return resp.json()
    _require_requests()
    with _guarded(url, proxy_url):
        resp = requests.get(url, headers=headers or {}, timeout=timeout,
                            proxies=_proxies(proxy_url), allow_redirects=False)
    _raise_for_status(resp)
    return resp.json()


# Redirect status codes we follow (MANUALLY — re-validating each hop).
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
# Headers stripped when a redirect crosses to a different origin, so a
# redirect can't exfiltrate the provider token / cookies to another host.
_SENSITIVE_HEADERS = frozenset({'authorization', 'cookie', 'proxy-authorization'})


def _origin(url):
    """(scheme, host, port) tuple for same-origin comparison across redirects."""
    from urllib.parse import urlsplit
    s = urlsplit((url or '').strip())
    return ((s.scheme or '').lower(), (s.hostname or '').lower(), s.port)


def _guarded_get_following_redirects(url, *, headers=None, timeout=120.0,
                                     proxy_url=None, max_redirects=5):
    """GET via requests, following 3xx redirects MANUALLY.

    ``requests``' own ``allow_redirects=True`` would only vet the FIRST URL
    through the SSRF guard, so a malicious / compromised endpoint could 302 to
    an internal or cloud-metadata address (e.g. 169.254.169.254, localhost) and
    escape it. Here every hop — including each ``Location`` — is re-validated and
    DNS-pinned via :func:`_guarded` before the next request is issued, and
    credentials are dropped on cross-origin hops.
    """
    from urllib.parse import urljoin
    hdrs = dict(headers or {})
    current = url
    for _hop in range(max_redirects + 1):
        with _guarded(current, proxy_url):
            resp = requests.get(current, headers=hdrs, timeout=timeout,
                                proxies=_proxies(proxy_url), allow_redirects=False)
        if resp.status_code not in _REDIRECT_STATUSES:
            return resp
        location = resp.headers.get('Location')
        if not location:
            return resp
        nxt = urljoin(current, location)
        if _origin(nxt) != _origin(current):
            for key in [k for k in hdrs if k.lower() in _SENSITIVE_HEADERS]:
                hdrs.pop(key, None)
        with contextlib.suppress(Exception):
            resp.close()
        current = nxt
    raise AiHttpError(0, f"Too many redirects fetching {url}")


def get_bytes(url, *, headers=None, timeout=120.0, proxy_url=None, impersonate=None):
    """GET raw bytes (binary media download). Returns ``(content, content_type)``.

    Used to materialize generated images/videos whose provider URLs are
    ephemeral (e.g. xAI ``imgen.x.ai/xai-tmp-*`` expire within minutes). The URL
    comes from a provider API response and may redirect to the provider CDN, so
    redirects ARE followed — but each hop is re-validated through the SSRF guard
    (see :func:`_guarded_get_following_redirects`), so a redirect can't reach an
    internal / metadata address.
    """
    if impersonate and IMPERSONATE_AVAILABLE:
        resp = _curl_get(url, headers=headers, timeout=timeout,
                         proxy_url=proxy_url, impersonate=impersonate)
        if resp.status_code >= 400:
            _raise_for_status(resp)
        return resp.content, (resp.headers.get('Content-Type') or '')
    _require_requests()
    resp = _guarded_get_following_redirects(
        url, headers=headers, timeout=timeout, proxy_url=proxy_url)
    if resp.status_code >= 400:
        _raise_for_status(resp)
    return resp.content, (resp.headers.get('Content-Type') or '')


def post_form(url, *, headers=None, data=None, timeout=60.0, proxy_url=None):
    """POST application/x-www-form-urlencoded (OAuth token endpoints)."""
    _require_requests()
    with _guarded(url, proxy_url):
        resp = requests.post(url, headers=headers or {}, data=data or {},
                            timeout=timeout, proxies=_proxies(proxy_url), allow_redirects=False)
    _raise_for_status(resp)
    return resp.json()


def post_multipart(url, *, headers=None, data=None, files=None, timeout=180.0,
                   proxy_url=None):
    """POST multipart/form-data (file uploads, e.g. OpenAI ``/images/edits``).

    *files* maps field name -> ``(filename, bytes, content_type)``; *data* maps
    field name -> str. Returns the parsed JSON response. The Content-Type header
    is dropped so ``requests`` sets the multipart boundary itself.
    """
    _require_requests()
    h = dict(headers or {})
    h.pop('Content-Type', None)
    h.pop('content-type', None)
    with _guarded(url, proxy_url):
        resp = requests.post(url, headers=h, data=data or {}, files=files or {},
                            timeout=timeout, proxies=_proxies(proxy_url), allow_redirects=False)
    _raise_for_status(resp)
    return resp.json()


def post_sse(url, *, headers=None, json_body=None, timeout=600.0, proxy_url=None,
             impersonate=None):
    """POST JSON and yield parsed SSE ``data:`` events as Python objects.

    Each yielded item is the JSON-decoded payload of one ``data:`` line.
    The terminal ``[DONE]`` sentinel is consumed and stops iteration. When
    *impersonate* is set and curl_cffi is available, the stream uses a browser
    TLS fingerprint; otherwise plain requests.
    """
    if impersonate and IMPERSONATE_AVAILABLE:
        yield from _curl_post_sse(url, headers=headers, json_body=json_body,
                                  timeout=timeout, proxy_url=proxy_url, impersonate=impersonate)
        return
    _require_requests()
    with _guarded(url, proxy_url):
        resp = requests.post(
            url, headers=headers or {}, json=json_body, timeout=timeout,
            proxies=_proxies(proxy_url), stream=True, allow_redirects=False,
        )
    # When the response omits a charset (e.g. the Codex backend sends
    # text/event-stream with no charset), requests can't decode and
    # iter_lines(decode_unicode=True) yields bytes — decode defensively below.
    if resp.encoding is None:
        resp.encoding = 'utf-8'
    try:
        _raise_for_status(resp)
        for raw_line in resp.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            if isinstance(raw_line, bytes):
                raw_line = raw_line.decode('utf-8', 'replace')
            line = raw_line.strip()
            if not line.startswith('data:'):
                continue
            payload = line[len('data:'):].strip()
            if payload == '[DONE]':
                break
            try:
                yield json.loads(payload)
            except (ValueError, TypeError):
                _logger.debug("Skipping non-JSON SSE line: %s", payload[:120])
                continue
    finally:
        resp.close()
