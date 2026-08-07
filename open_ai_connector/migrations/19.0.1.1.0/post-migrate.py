# -*- coding: utf-8 -*-
"""Seed OAuth endpoint defaults onto providers, then backfill credentials.

The provider xmlids are owned by ai_provider_data.xml (noupdate=1), so a data
file can't set their new OAuth fields on -u — only an ORM write does. We set
them here, then copy onto any existing OAuth credential whose fields are blank
so the form shows them too.
"""
from odoo import api, SUPERUSER_ID

PROVIDER_OAUTH = {
    'openai-codex': {
        'auth_type': 'oauth_device_code',
        'oauth_client_id': 'app_EMoamEEZ73f0CkXaXp7hrann',
        'oauth_device_authorization_url': 'https://auth.openai.com/api/accounts/deviceauth/usercode',
        'oauth_token_url': 'https://auth.openai.com/api/accounts/deviceauth/token',
    },
    'qwen-oauth': {
        'oauth_client_id': 'f0304373b74a44d2b584a3fb70ca9e56',
        'oauth_token_url': 'https://chat.qwen.ai/api/v1/oauth2/token',
    },
    'google-gemini-cli': {
        #'oauth_client_id': '681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com',
        #'oauth_client_secret': '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',
        'oauth_auth_url': 'https://accounts.google.com/o/oauth2/v2/auth',
        'oauth_token_url': 'https://oauth2.googleapis.com/token',
        'oauth_scopes': ('https://www.googleapis.com/auth/cloud-platform '
                         'https://www.googleapis.com/auth/userinfo.email '
                         'https://www.googleapis.com/auth/userinfo.profile'),
    },
    'minimax-oauth': {
        'oauth_client_id': '78257093-7e40-4613-99e0-527b14b39113',
        'oauth_auth_url': 'https://api.minimax.io/oauth/code',
        'oauth_token_url': 'https://api.minimax.io/oauth/token',
        'oauth_scopes': 'group_id profile model.completion',
    },
}
_CRED_FIELDS = ('oauth_client_id', 'oauth_client_secret', 'oauth_auth_url',
                'oauth_token_url', 'oauth_device_authorization_url', 'oauth_scopes')


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Provider = env['ai.provider']
    for code, vals in PROVIDER_OAUTH.items():
        prov = Provider.search([('code', '=', code)], limit=1)
        if prov:
            prov.write(vals)
    for cred in env['ai.credential'].search([
            ('auth_type', 'in', ('oauth_external', 'oauth_device_code'))]):
        provider = cred.provider_id
        backfill = {f: provider[f] for f in _CRED_FIELDS
                    if not cred[f] and provider[f]}
        if backfill:
            cred.write(backfill)
