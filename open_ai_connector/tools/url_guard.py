# -*- coding: utf-8 -*-
"""Outbound-URL safety guard (SSRF mitigation).

Every outbound request the connector makes goes through ``http_client``; this
module is the single chokepoint that vets the target (and proxy) URL before the
request leaves the server. It blocks the things that are never a legitimate AI
endpoint — non-HTTP(S) schemes and cloud link-local / metadata addresses
(169.254.0.0/16, fe80::/10, metadata.google.internal, …) — while deliberately
allowing loopback / private ranges so self-hosted providers (Ollama, vLLM on
localhost or the LAN) keep working.

Set ``open_ai_connector.block_private_endpoints`` truthy (handled by the caller,
which passes ``block_private=True``) to additionally refuse loopback/RFC-1918
targets for a locked-down deployment with no local providers.

``safe_resolve`` performs the authoritative DNS resolution + vetting and returns
the IP to pin for the connection (see ``dns_pin``), so the address the guard
approves is exactly the address ``requests`` connects to — no rebinding window.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from .http_client import AiHttpError

# Hostnames that resolve to cloud metadata services — never a real AI endpoint.
_METADATA_HOSTS = frozenset({
    'metadata.google.internal', 'metadata.goog', 'metadata',
})
_ALLOWED_SCHEMES = frozenset({'http', 'https'})
# Schemes a proxy may legitimately use.
_ALLOWED_PROXY_SCHEMES = frozenset({'http', 'https', 'socks5', 'socks5h', 'socks4', 'socks4a'})


def _ip_is_blocked(ip_str, *, block_private):
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    # Unwrap IPv4-mapped IPv6 (::ffff:a.b.c.d) so an embedded internal IPv4 is
    # caught — a classic guard bypass.
    mapped = getattr(addr, 'ipv4_mapped', None)
    if mapped is not None:
        addr = mapped
    # ALWAYS blocked, never a legitimate endpoint: link-local (covers
    # 169.254.169.254 + fe80::/10), multicast, unspecified.
    if addr.is_link_local or addr.is_multicast or addr.is_unspecified:
        return True
    # Loopback + private (incl. IPv6 ::1): allowed by default so self-hosted
    # providers work; refused only under the locked-down policy.
    if block_private and (addr.is_loopback or addr.is_private):
        return True
    return False


def _host_allowed(host, allowlist):
    """True when *host* equals or is a subdomain of any allowlist entry."""
    host = (host or '').lower().rstrip('.')
    for dom in allowlist:
        dom = (dom or '').strip().lower().rstrip('.')
        if dom and (host == dom or host.endswith('.' + dom)):
            return True
    return False


def validate_outbound_url(url, *, block_private=False, allowlist=None):
    """Raise AiHttpError on scheme / allowlist / metadata / literal-IP violations.

    Does NOT resolve hostnames — the authoritative resolve+vet (and the IP to
    connect to) is produced by ``safe_resolve`` so the vetted address and the
    connected address are guaranteed identical.
    """
    parsed = urlparse((url or '').strip())
    scheme = (parsed.scheme or '').lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise AiHttpError(0, "Blocked outbound request: unsupported URL scheme.")
    host = (parsed.hostname or '').lower().rstrip('.')
    if not host:
        raise AiHttpError(0, "Blocked outbound request: missing host.")
    # Fail closed on non-ASCII/IDN hosts: urllib3 IDNA-encodes to punycode before
    # resolving, which would diverge from our pin key and reopen rebinding.
    if not host.isascii():
        raise AiHttpError(0, "Blocked outbound request: non-ASCII host.")
    if allowlist and not _host_allowed(host, allowlist):
        raise AiHttpError(0, "Blocked outbound request: host not in the allowlist.")
    if host in _METADATA_HOSTS:
        raise AiHttpError(0, "Blocked outbound request: metadata endpoint.")
    # Literal IP — vet directly (no DNS needed).
    try:
        if _ip_is_blocked(host, block_private=block_private):
            raise AiHttpError(0, "Blocked outbound request: internal address.")
    except ValueError:
        pass


def host_port(url, *, default_port=None):
    """Return (host, port) for a URL ('' host if absent)."""
    parsed = urlparse((url or '').strip())
    host = (parsed.hostname or '').lower().rstrip('.')
    scheme = (parsed.scheme or '').lower()
    port = parsed.port or default_port or (443 if scheme == 'https' else 80)
    return host, port


def safe_resolve(host, port, *, block_private=False):
    """Resolve *host* and return a single vetted IP to pin the connection to.

    Refuses the call (raise) if the host resolves to ANY blocked address — this
    also defeats round-robin rebinding (public + metadata in one record set).
    Returns None for a literal IP (already vetted by validate_outbound_url) or
    when resolution fails (left for requests to surface normally).
    """
    host = (host or '').lower().rstrip('.')
    if not host:
        return None
    try:
        ipaddress.ip_address(host)
        return None  # literal IP: connect target is the IP itself, nothing to pin
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError:
        return None
    addrs = [info[4][0] for info in infos]
    for ip in addrs:
        if _ip_is_blocked(ip, block_private=block_private):
            raise AiHttpError(
                0, "Blocked outbound request: host resolves to an internal address.")
    return addrs[0] if addrs else None


def validate_proxy_url(proxy_url, *, block_private=False):
    """Vet a proxy: enforce a scheme allowlist and reject internal/metadata hosts.

    Returns (host, port) so the caller can pin the proxy's DNS too. Fails closed
    on an unparseable value.
    """
    raw = (proxy_url or '').strip()
    if not raw:
        return None
    parsed = urlparse(raw if '://' in raw else f'//{raw}')
    scheme = (parsed.scheme or '').lower()
    if scheme and scheme not in _ALLOWED_PROXY_SCHEMES:
        raise AiHttpError(0, "Blocked proxy: unsupported scheme.")
    host = (parsed.hostname or '').lower().rstrip('.')
    if not host:
        raise AiHttpError(0, "Blocked proxy: could not parse host.")
    if not host.isascii():
        raise AiHttpError(0, "Blocked proxy: non-ASCII host.")
    if host in _METADATA_HOSTS:
        raise AiHttpError(0, "Blocked proxy: metadata endpoint.")
    try:
        if _ip_is_blocked(host, block_private=block_private):
            raise AiHttpError(0, "Blocked proxy: internal address.")
    except ValueError:
        pass
    return host, (parsed.port or 1080)
