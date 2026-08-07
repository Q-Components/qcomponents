# -*- coding: utf-8 -*-
"""Generic OAuth2 helpers — refresh, device-code, authorization-code (PKCE).

Pure functions over plain dicts. The ai.credential model stores the endpoints
(auth_url / token_url / device_authorization_url), client_id/secret and scopes,
then calls these to obtain/refresh tokens. Provider-specific quirks beyond
standard OAuth2 are configured via the credential's ``oauth_extra`` JSON.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from . import http_client

REFRESH_SKEW_SECONDS = 120


def _now():
    return datetime.now(timezone.utc)


def is_expired(expiry_iso, skew=None):
    """True when *expiry_iso* (ISO-8601) is within *skew* seconds of now.

    *skew* defaults to REFRESH_SKEW_SECONDS (reactive, just-in-time refresh).
    The proactive cron passes a larger lead so tokens refresh ahead of expiry.
    """
    if not expiry_iso:
        return False
    if skew is None:
        skew = REFRESH_SKEW_SECONDS
    try:
        exp = datetime.fromisoformat(expiry_iso)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return True
    return _now() + timedelta(seconds=skew) >= exp


def needs_refresh(cred: dict, lead_seconds=None) -> bool:
    """True when this OAuth credential should be refreshed now.

    A refresh is possible only when a refresh_token is present. The access
    token is considered stale if missing, or expiring within *lead_seconds*
    (default skew). Used by both the reactive path and the proactive cron.
    """
    if not cred.get('oauth_refresh_token'):
        return False
    if not cred.get('oauth_access_token'):
        return True
    return is_expired(cred.get('oauth_token_expiry'), skew=lead_seconds)


def _expiry_from_expires_in(expires_in):
    try:
        secs = int(expires_in)
    except (ValueError, TypeError):
        secs = 3600
    return (_now() + timedelta(seconds=secs)).isoformat()


def _token_dict(payload):
    out = {'oauth_access_token': payload.get('access_token')}
    if payload.get('refresh_token'):
        out['oauth_refresh_token'] = payload['refresh_token']
    if payload.get('expires_in'):
        out['oauth_token_expiry'] = _expiry_from_expires_in(payload['expires_in'])
    return out


def _uses_json_token(cred):
    """Anthropic's OAuth token endpoint speaks JSON, not form-urlencoded."""
    return cred.get('oauth_flavor') == 'anthropic'


def _post_token(cred, data):
    """POST to the token endpoint using the dialect this provider expects.

    Anthropic's token endpoint is JSON AND fronted by Cloudflare, so it's sent
    with a browser TLS fingerprint (curl_cffi 'chrome') to match Claude Code —
    plain python-requests can be challenged. Falls back to requests if curl_cffi
    is unavailable.
    """
    token_url = cred.get('oauth_token_url')
    if _uses_json_token(cred):
        return http_client.post_json(
            token_url, headers={'Accept': 'application/json'}, json_body=data,
            proxy_url=cred.get('proxy_url'), max_retries=1, impersonate='chrome')
    return http_client.post_form(token_url, data=data, proxy_url=cred.get('proxy_url'))


def discover_oidc(discovery_url, proxy_url=None):
    """Fetch an OpenID Connect discovery document → {authorize, token} endpoints.

    xAI (and any standards-compliant IdP) publishes its endpoints at
    ``.well-known/openid-configuration`` rather than hard-coding them, so they
    can rotate without a code change.
    """
    if not discovery_url:
        return {}
    doc = http_client.get_json(discovery_url, timeout=15.0, proxy_url=proxy_url)
    if not isinstance(doc, dict):
        return {}
    return {
        'oauth_auth_url': doc.get('authorization_endpoint') or '',
        'oauth_token_url': doc.get('token_endpoint') or '',
    }


def refresh(cred: dict) -> dict:
    """Exchange the refresh_token for a fresh access_token. Returns token fields."""
    token_url = cred.get('oauth_token_url')
    refresh_token = cred.get('oauth_refresh_token')
    if not token_url or not refresh_token:
        raise http_client.AiHttpError(0, "Cannot refresh: missing token URL or refresh token.")
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': cred.get('oauth_client_id') or '',
    }
    if cred.get('oauth_client_secret'):
        data['client_secret'] = cred['oauth_client_secret']
    payload = _post_token(cred, data)
    return _token_dict(payload)


def ensure_fresh(cred: dict):
    """Return refreshed token fields if the access token is expired, else None."""
    if cred.get('oauth_access_token') and not is_expired(cred.get('oauth_token_expiry')):
        return None
    if not cred.get('oauth_refresh_token'):
        return None
    return refresh(cred)


# ── Device code flow ────────────────────────────────────────────────────
def device_code_start(cred: dict) -> dict:
    """Begin the device-authorization flow. Returns the device-code response."""
    url = cred.get('oauth_device_authorization_url')
    if not url:
        raise http_client.AiHttpError(0, "No device authorization URL configured.")
    data = {'client_id': cred.get('oauth_client_id') or ''}
    if cred.get('oauth_scopes'):
        data['scope'] = cred['oauth_scopes']
    return http_client.post_form(url, data=data, proxy_url=cred.get('proxy_url'))


def device_code_poll(cred: dict, device_code: str) -> dict:
    """Poll once for the device-code token. Returns token fields or {'pending': ...}."""
    token_url = cred.get('oauth_token_url')
    if not token_url:
        raise http_client.AiHttpError(0, "No token URL configured.")
    data = {
        'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
        'device_code': device_code,
        'client_id': cred.get('oauth_client_id') or '',
    }
    if cred.get('oauth_client_secret'):
        data['client_secret'] = cred['oauth_client_secret']
    try:
        payload = http_client.post_form(token_url, data=data, proxy_url=cred.get('proxy_url'))
    except http_client.AiHttpError as exc:
        body = exc.body if isinstance(exc.body, dict) else {}
        err = body.get('error')
        if err in ('authorization_pending', 'slow_down'):
            return {'pending': err}
        raise
    return _token_dict(payload)


# ── OpenAI Codex device flow (custom, JSON-based — not RFC-8628) ─────────
# OpenAI's ChatGPT/Codex device login does NOT speak standard OAuth2 device
# code. It is a 3-call JSON flow:
#   1. POST {usercode_url}  json {client_id}            -> {device_auth_id, user_code, interval}
#   2. user opens CODEX_VERIFICATION_URI, enters user_code
#   3. POST {poll_url}      json {device_auth_id, user_code}
#        -> 200 {authorization_code, code_verifier}  (403/404 while pending)
#   4. POST {token_url}     form authorization_code     -> {access_token, refresh_token}
# The poll URL is the usercode URL with the trailing segment swapped to
# 'token'; the redirect_uri is fixed to {issuer}/deviceauth/callback.
CODEX_VERIFICATION_URI = "https://auth.openai.com/codex/device"


def _codex_issuer(usercode_url):
    from urllib.parse import urlsplit
    parts = urlsplit(usercode_url)
    return f"{parts.scheme}://{parts.netloc}"


def codex_device_start(cred: dict) -> dict:
    """Codex step 1 — request a user code (JSON). Returns device handle fields."""
    url = cred.get('oauth_device_authorization_url')
    if not url:
        raise http_client.AiHttpError(0, "No device authorization URL configured.")
    payload = http_client.post_json(
        url, json_body={'client_id': cred.get('oauth_client_id') or ''},
        timeout=20.0, proxy_url=cred.get('proxy_url'), max_retries=1)
    return {
        'device_auth_id': payload.get('device_auth_id'),
        'user_code': payload.get('user_code'),
        'verification_uri': CODEX_VERIFICATION_URI,
        'interval': payload.get('interval'),
    }


def codex_device_poll(cred: dict, device_auth_id: str, user_code: str) -> dict:
    """Codex steps 3-4 — poll, then exchange. Token fields or {'pending': ...}."""
    usercode_url = cred.get('oauth_device_authorization_url') or ''
    if not usercode_url or not device_auth_id:
        raise http_client.AiHttpError(0, "Start the Codex device flow first.")
    poll_url = usercode_url.rsplit('/', 1)[0] + '/token'
    try:
        code_resp = http_client.post_json(
            poll_url,
            json_body={'device_auth_id': device_auth_id, 'user_code': user_code},
            timeout=20.0, proxy_url=cred.get('proxy_url'), max_retries=0)
    except http_client.AiHttpError as exc:
        if exc.status_code in (403, 404):
            return {'pending': 'authorization_pending'}
        raise
    authorization_code = code_resp.get('authorization_code')
    code_verifier = code_resp.get('code_verifier')
    if not authorization_code or not code_verifier:
        return {'pending': 'authorization_pending'}
    issuer = _codex_issuer(usercode_url)
    token_url = cred.get('oauth_token_url') or f"{issuer}/oauth/token"
    data = {
        'grant_type': 'authorization_code',
        'code': authorization_code,
        'redirect_uri': f"{issuer}/deviceauth/callback",
        'client_id': cred.get('oauth_client_id') or '',
        'code_verifier': code_verifier,
    }
    payload = http_client.post_form(token_url, data=data, proxy_url=cred.get('proxy_url'))
    return _token_dict(payload)


# ── MiniMax user-code flow (custom) ─────────
# MiniMax is a 2-call PKCE "user code" flow (NOT RFC-8628 device code):
#   1. POST {oauth_auth_url}  form {response_type=code, client_id, scope,
#        code_challenge, code_challenge_method=S256, state}
#        -> {user_code, verification_uri, expired_in, interval, state}
#   2. user opens verification_uri, enters user_code
#   3. POST {oauth_token_url} form {grant_type=...:user_code, client_id,
#        user_code, code_verifier}  (poll)
#        -> {status: pending|success|error, access_token, refresh_token, expired_in}
MINIMAX_GRANT_TYPE = 'urn:ietf:params:oauth:grant-type:user_code'


def _minimax_expiry_iso(expired_in):
    """MiniMax 'expired_in' is either a unix-ms absolute time or a TTL in seconds."""
    try:
        raw = int(expired_in)
    except (ValueError, TypeError):
        return _expiry_from_expires_in(3600)
    now = _now()
    now_ms = int(now.timestamp() * 1000)
    if raw > now_ms // 2:           # plausibly a unix-ms timestamp
        return datetime.fromtimestamp(raw / 1000.0, tz=timezone.utc).isoformat()
    return (now + timedelta(seconds=max(1, raw))).isoformat()


def minimax_start(cred: dict) -> dict:
    """MiniMax step 1 — request a user code (PKCE). Returns handle fields."""
    auth_url = cred.get('oauth_auth_url')
    if not auth_url:
        raise http_client.AiHttpError(0, "No authorization URL configured.")
    verifier, challenge = make_pkce()
    state = secrets.token_urlsafe(16)
    data = {
        'response_type': 'code',
        'client_id': cred.get('oauth_client_id') or '',
        'scope': cred.get('oauth_scopes') or '',
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
        'state': state,
    }
    payload = http_client.post_form(auth_url, data=data, proxy_url=cred.get('proxy_url'))
    if payload.get('state') and payload['state'] != state:
        raise http_client.AiHttpError(0, "MiniMax OAuth state mismatch (possible CSRF).")
    return {
        'user_code': payload.get('user_code'),
        'verification_uri': payload.get('verification_uri'),
        'code_verifier': verifier,
        'interval': payload.get('interval'),
        'expired_in': payload.get('expired_in'),
    }


def minimax_poll(cred: dict, user_code: str, code_verifier: str) -> dict:
    """MiniMax step 3 — poll once. Token fields, or {'pending': ...}."""
    token_url = cred.get('oauth_token_url')
    if not token_url or not user_code:
        raise http_client.AiHttpError(0, "Start the MiniMax flow first.")
    data = {
        'grant_type': MINIMAX_GRANT_TYPE,
        'client_id': cred.get('oauth_client_id') or '',
        'user_code': user_code,
        'code_verifier': code_verifier or '',
    }
    try:
        payload = http_client.post_form(token_url, data=data, proxy_url=cred.get('proxy_url'))
    except http_client.AiHttpError:
        raise
    status = payload.get('status')
    if status == 'error':
        raise http_client.AiHttpError(0, "MiniMax OAuth reported an error — try again.")
    if status != 'success':
        return {'pending': status or 'pending'}
    if not payload.get('access_token'):
        return {'pending': 'pending'}
    out = {'oauth_access_token': payload.get('access_token')}
    if payload.get('refresh_token'):
        out['oauth_refresh_token'] = payload['refresh_token']
    if payload.get('expired_in') is not None:
        out['oauth_token_expiry'] = _minimax_expiry_iso(payload['expired_in'])
    return out


# ── Qwen device flow (RFC-8628 device code + PKCE) ──────────────────────
# Qwen Code's OAuth: device authorization grant WITH PKCE. The token response
# carries a ``resource_url`` that determines the inference base (https://<rurl>/v1).
QWEN_DEVICE_GRANT_TYPE = 'urn:ietf:params:oauth:grant-type:device_code'


def qwen_device_start(cred: dict) -> dict:
    """Qwen step 1 — device authorization (PKCE). Returns device handle fields."""
    url = cred.get('oauth_device_authorization_url')
    if not url:
        raise http_client.AiHttpError(0, "No device authorization URL configured.")
    verifier, challenge = make_pkce()
    data = {
        'client_id': cred.get('oauth_client_id') or '',
        'scope': cred.get('oauth_scopes') or '',
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    }
    payload = http_client.post_form(url, data=data, proxy_url=cred.get('proxy_url'))
    return {
        'device_code': payload.get('device_code'),
        'user_code': payload.get('user_code'),
        'verification_uri': (payload.get('verification_uri_complete')
                             or payload.get('verification_uri')),
        'code_verifier': verifier,
        'interval': payload.get('interval'),
    }


def qwen_device_poll(cred: dict, device_code: str, code_verifier: str) -> dict:
    """Qwen poll — token fields (+ qwen_base_url), or {'pending': ...}."""
    token_url = cred.get('oauth_token_url')
    if not token_url or not device_code:
        raise http_client.AiHttpError(0, "Start the Qwen device flow first.")
    data = {
        'grant_type': QWEN_DEVICE_GRANT_TYPE,
        'client_id': cred.get('oauth_client_id') or '',
        'device_code': device_code,
        'code_verifier': code_verifier or '',
    }
    try:
        payload = http_client.post_form(token_url, data=data, proxy_url=cred.get('proxy_url'))
    except http_client.AiHttpError as exc:
        body = exc.body if isinstance(exc.body, dict) else {}
        if body.get('error') in ('authorization_pending', 'slow_down'):
            return {'pending': body['error']}
        raise
    out = _token_dict(payload)
    resource_url = (payload.get('resource_url') or '').strip()
    if resource_url:
        host = resource_url if '://' in resource_url else 'https://' + resource_url
        out['qwen_base_url'] = host.rstrip('/') + ('' if host.rstrip('/').endswith('/v1') else '/v1')
    return out


# ── Authorization code + PKCE ───────────────────────────────────────────
def make_pkce():
    """Return (code_verifier, code_challenge) for PKCE S256."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b'=').decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b'=').decode()
    return verifier, challenge


def external_auth_url(cred: dict, redirect_uri: str, state: str):
    """Build the authorization-code URL (PKCE). Returns (url, code_verifier).

    Merges any provider-specific extra authorize params (e.g. Codex's
    ``codex_cli_simplified_flow``/``prompt=login``, Google's ``access_type``).
    """
    from urllib.parse import urlencode
    auth_url = cred.get('oauth_auth_url')
    if not auth_url:
        raise http_client.AiHttpError(0, "No authorization URL configured.")
    verifier, challenge = make_pkce()
    params = {
        'response_type': 'code',
        'client_id': cred.get('oauth_client_id') or '',
        'redirect_uri': redirect_uri,
        'state': state,
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    }
    if cred.get('oauth_scopes'):
        params['scope'] = cred['oauth_scopes']
    extra = cred.get('oauth_extra_authorize_params')
    if isinstance(extra, dict):
        params.update({k: str(v) for k, v in extra.items() if v is not None})
    sep = '&' if '?' in auth_url else '?'
    return f"{auth_url}{sep}{urlencode(params)}", verifier


def parse_callback(text: str) -> dict:
    """Parse a pasted OAuth redirect into {code, state, error, error_description}.

    Accepts: a full redirect URL
    (``http://localhost:1455/auth/callback?code=..&state=..``), a query string
    with or without a leading ``?``, or a bare authorization code.
    """
    from urllib.parse import urlparse, parse_qs
    out = {'code': None, 'state': None, 'error': None, 'error_description': None}
    s = (text or '').strip()
    if not s:
        return out
    if s.startswith('http://') or s.startswith('https://'):
        query = urlparse(s).query
    elif s.startswith('?'):
        query = s[1:]
    elif '=' in s:
        query = s
    else:
        out['code'] = s            # bare authorization code
        return out
    params = parse_qs(query, keep_blank_values=False)
    for key in out:
        if params.get(key):
            out[key] = params[key][0]
    return out


def exchange_code(cred: dict, code: str, code_verifier: str, redirect_uri: str,
                  state: str = None) -> dict:
    """Exchange an authorization code for tokens. Returns token fields.

    Anthropic's OAuth (claude.ai) is non-standard in two ways:
      • the authorization code is returned as ``<code>#<state>`` — split it; and
      • the token endpoint REQUIRES the ``state`` field in the exchange body,
        rejecting the request as "Invalid request format" when it's absent.
    We apply both ONLY for the anthropic flavor; other providers use the plain
    authorization-code body. The state sent is the one embedded after ``#`` if
    present, else the caller-supplied *state* (the value we sent at authorize).
    """
    token_url = cred.get('oauth_token_url')
    if not token_url:
        raise http_client.AiHttpError(0, "No token URL configured.")
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
        'client_id': cred.get('oauth_client_id') or '',
        'code_verifier': code_verifier,
    }
    if cred.get('oauth_flavor') == 'anthropic':
        before, sep, after = (code or '').partition('#')
        if sep:
            data['code'] = before
        eff_state = (after if sep and after else None) or state
        if eff_state:
            data['state'] = eff_state
    if cred.get('oauth_client_secret'):
        data['client_secret'] = cred['oauth_client_secret']
    payload = _post_token(cred, data)
    return _token_dict(payload)
