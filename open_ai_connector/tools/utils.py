# -*- coding: utf-8 -*-
"""Request quirks & URL helpers."""
from __future__ import annotations

from urllib.parse import urlparse


def base_url_hostname(base_url: str) -> str:
    """Return the lowercased hostname for a base URL, or '' if absent."""
    raw = (base_url or '').strip()
    if not raw:
        return ''
    parsed = urlparse(raw if '://' in raw else f'//{raw}')
    return (parsed.hostname or '').lower().rstrip('.')


def base_url_host_matches(base_url: str, domain: str) -> bool:
    """True when the base URL's hostname is *domain* or a subdomain of it."""
    hostname = base_url_hostname(base_url)
    if not hostname:
        return False
    domain = (domain or '').strip().lower().rstrip('.')
    if not domain:
        return False
    return hostname == domain or hostname.endswith('.' + domain)


def model_forces_max_completion_tokens(model: str) -> bool:
    """True for OpenAI model families that reject ``max_tokens``.

    Those families (gpt-4o/gpt-4.1/gpt-5/o1/o3/o4) require
    ``max_completion_tokens`` on /v1/chat/completions instead. Handles vendor
    prefixes like ``openai/gpt-5.4``.
    """
    m = (model or '').strip().lower()
    if not m:
        return False
    if '/' in m:
        m = m.rsplit('/', 1)[-1]
    return (
        m.startswith('gpt-4o')
        or m.startswith('gpt-4.1')
        or m.startswith('gpt-5')
        or m.startswith('o1')
        or m.startswith('o3')
        or m.startswith('o4')
    )


def join_url(base_url: str, path: str) -> str:
    """Join a base URL and a path with exactly one slash."""
    return (base_url or '').rstrip('/') + '/' + (path or '').lstrip('/')


def normalize_proxy_url(proxy_url: str | None) -> str | None:
    """Normalize SOCKS proxy aliases for requests/httpx compatibility."""
    candidate = str(proxy_url or '').strip()
    if not candidate:
        return None
    if candidate.lower().startswith('socks://'):
        return f"socks5://{candidate[len('socks://'):]}"
    return candidate
