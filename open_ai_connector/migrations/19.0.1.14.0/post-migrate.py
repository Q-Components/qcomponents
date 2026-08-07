# -*- coding: utf-8 -*-
"""Upstream login flows: Codex→PKCE, Claude.ai OAuth, xAI OIDC discovery.

The OAuth seed file is noupdate=0 (re-applied on -u), so these should land from
data alone — but the noupdate gotcha has bitten this module before, so ORM-write
the load-bearing changes here to guarantee the live DB matches. Idempotent.
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Codex: device-code → Authorization Code + PKCE (loopback localhost:1455).
    codex = env.ref('open_ai_connector.provider_openai_codex', raise_if_not_found=False)
    if codex:
        codex.write({
            'auth_type': 'oauth_external',
            'oauth_flavor': 'standard',
            'oauth_auth_url': 'https://auth.openai.com/oauth/authorize',
            'oauth_token_url': 'https://auth.openai.com/oauth/token',
            'oauth_scopes': 'openid email profile offline_access',
            'oauth_redirect_uri': 'http://localhost:1455/auth/callback',
            'oauth_extra_authorize_params':
                '{"id_token_add_organizations": "true", "codex_cli_simplified_flow": "true"}',
        })

    # xAI: resolve endpoints via OIDC discovery at login.
    xai = env.ref('open_ai_connector.provider_xai_oauth', raise_if_not_found=False)
    if xai and not xai.oauth_discovery_url:
        xai.write({'oauth_discovery_url':
                   'https://auth.x.ai/.well-known/openid-configuration'})

    # Claude (claude.ai OAuth): created by the data files on -u; ensure the
    # OAuth config in case the record pre-existed (e.g. partial state).
    claude = env.ref('open_ai_connector.provider_claude_oauth', raise_if_not_found=False)
    if claude:
        claude.write({
            'oauth_flavor': 'anthropic',
            'oauth_client_id': '9d1c250a-e61b-44d9-88ed-5944d1962f5e',
            'oauth_auth_url': 'https://claude.ai/oauth/authorize',
            'oauth_token_url': 'https://api.anthropic.com/v1/oauth/token',
            'oauth_scopes': ('user:profile user:inference user:sessions:claude_code '
                             'user:mcp_servers user:file_upload'),
            'oauth_redirect_uri': 'http://localhost:54545/callback',
            'oauth_extra_authorize_params': '{"code": "true"}',
        })
