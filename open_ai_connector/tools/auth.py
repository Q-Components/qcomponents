# -*- coding: utf-8 -*-
"""Credential resolution — turn a credential into request auth.

Pure functions (no ORM). The caller (ai.credential model) passes plain dicts and
is responsible for refreshing OAuth tokens *before* calling resolve(). Implements
the per-auth_type attachment logic (Bearer, x-api-key, AWS SigV4, OAuth, Copilot).
"""
from __future__ import annotations

import json

from .http_client import AiHttpError

ANTHROPIC_VERSION = '2023-06-01'

# Claude Code client signature. An OAuth
# token from a claude.ai login is scoped to Claude Code: Anthropic's Messages API
# only accepts it when the request presents the Claude-Code beta flags + client
# fingerprint headers (and the "You are Claude Code…" system prefix, injected by
# the transport). Values match Claude Code 2.1.63 / @anthropic-ai/sdk 0.74.0.
CLAUDE_CODE_UA = 'claude-cli/2.1.63 (external, cli)'
CLAUDE_CODE_BETA = (
    'claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14,'
    'context-management-2025-06-27,prompt-caching-scope-2026-01-05,'
    'structured-outputs-2025-12-15,fast-mode-2026-02-01,redact-thinking-2026-02-12,'
    'token-efficient-tools-2026-03-28')


def _parse_extra_headers(extra_headers):
    if not extra_headers:
        return {}
    if isinstance(extra_headers, dict):
        return extra_headers
    try:
        data = json.loads(extra_headers)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def resolve(provider: dict, cred: dict) -> dict:
    """Return {'headers', 'base_url', 'proxy_url', 'boto3_session'} for a call.

    *provider* and *cred* are plain dicts. OAuth tokens in *cred* must already be
    fresh (the model refreshes them before calling).
    """
    auth_type = provider.get('auth_type')
    api_mode = provider.get('api_mode')
    base_url = (cred.get('base_url') or provider.get('base_url') or '').strip()
    headers = {'Content-Type': 'application/json'}
    headers.update(provider.get('default_headers') or {})
    proxy_url = cred.get('proxy_url') or None
    result = {'headers': headers, 'base_url': base_url,
              'proxy_url': proxy_url, 'boto3_session': None}

    if auth_type == 'aws_sdk':
        result['boto3_session'] = _aws_session(cred)
        return result

    if auth_type == 'external_process':
        raise AiHttpError(0, "Provider uses an external process (Copilot ACP) — "
                             "not supported by the Odoo connector.")

    # Resolve the bearer token from the right field per auth_type.
    if auth_type in ('oauth_external', 'oauth_device_code'):
        token = cred.get('oauth_access_token')
    else:  # api_key, copilot
        token = cred.get('api_key')

    if not token:
        raise AiHttpError(0, "No credential/token configured for this provider.")

    # Anthropic-protocol providers normally authenticate with x-api-key. But an
    # OAuth token from a claude.ai login (Pro/Max) is NOT an API key — it's a
    # Bearer token, and the Messages API only accepts it with the Claude-Code
    # OAuth beta headers. Everything
    # else uses Authorization: Bearer.
    if api_mode == 'anthropic_messages':
        if auth_type in ('oauth_external', 'oauth_device_code'):
            # OAuth tokens authenticate via Bearer (not x-api-key).
            headers['Authorization'] = f'Bearer {token}'
            headers['anthropic-version'] = ANTHROPIC_VERSION
            # The full Claude Code signature is ONLY for real Claude (claude.ai
            # OAuth, oauth_flavor='anthropic'). Other anthropic-protocol OAuth
            # providers (e.g. MiniMax /anthropic) must NOT get the claude-cli UA,
            # claude-code beta flags, or the "You are Claude Code…" system prefix.
            if provider.get('oauth_flavor') == 'anthropic':
                headers['anthropic-beta'] = CLAUDE_CODE_BETA
                headers['User-Agent'] = CLAUDE_CODE_UA
                headers['X-App'] = 'cli'
                headers['X-Stainless-Retry-Count'] = '0'
                headers['X-Stainless-Runtime'] = 'node'
                headers['X-Stainless-Lang'] = 'js'
                headers['X-Stainless-Package-Version'] = '0.74.0'
                headers['X-Stainless-Timeout'] = '600'
        else:
            headers['x-api-key'] = token
            headers['anthropic-version'] = ANTHROPIC_VERSION
    else:
        headers['Authorization'] = f'Bearer {token}'

    if auth_type == 'copilot':
        # Editor attribution headers GitHub Copilot expects.
        headers.setdefault('Copilot-Integration-Id', 'vscode-chat')
        headers.setdefault('Editor-Version', 'OdooAIConnector/19.0')

    headers.update(_parse_extra_headers(cred.get('extra_headers')))
    return result


def _aws_session(cred):
    try:
        import boto3
    except ImportError:
        raise AiHttpError(0, "AWS Bedrock requires the 'boto3' Python package. "
                             "Install it on the Odoo server (pip install boto3).")
    kwargs = {'region_name': cred.get('aws_region') or 'us-east-1'}
    if cred.get('aws_access_key_id') and cred.get('aws_secret_access_key'):
        kwargs['aws_access_key_id'] = cred['aws_access_key_id']
        kwargs['aws_secret_access_key'] = cred['aws_secret_access_key']
        if cred.get('aws_session_token'):
            kwargs['aws_session_token'] = cred['aws_session_token']
    # else: fall back to the default boto3 credential chain (instance role, etc.)
    return boto3.Session(**kwargs)
