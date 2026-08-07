# -*- coding: utf-8 -*-
"""Wire Qwen (device+PKCE) and MiniMax (user-code) OAuth login flows.

Both were seeded as oauth_external (no working server-side login). Switch them to
oauth_device_code with the right flavor + endpoints so the wizard drives the
real flow. The oauth seed file is noupdate=0 (re-applied on -u), so this is
belt-and-suspenders — but the noupdate gotcha has bitten before. Idempotent.
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    qwen = env.ref('open_ai_connector.provider_qwen_oauth', raise_if_not_found=False)
    if qwen:
        qwen.write({
            'auth_type': 'oauth_device_code',
            'oauth_flavor': 'qwen',
            'oauth_client_id': 'f0304373b74a44d2b584a3fb70ca9e56',
            'oauth_device_authorization_url': 'https://chat.qwen.ai/api/v1/oauth2/device/code',
            'oauth_token_url': 'https://chat.qwen.ai/api/v1/oauth2/token',
            'oauth_scopes': 'openid profile email model.completion',
        })

    minimax = env.ref('open_ai_connector.provider_minimax_oauth', raise_if_not_found=False)
    if minimax:
        minimax.write({
            'auth_type': 'oauth_device_code',
            'oauth_flavor': 'minimax',
            'oauth_client_id': '78257093-7e40-4613-99e0-527b14b39113',
            'oauth_auth_url': 'https://api.minimax.io/oauth/code',
            'oauth_token_url': 'https://api.minimax.io/oauth/token',
            'oauth_scopes': 'group_id profile model.completion',
        })
