# -*- coding: utf-8 -*-
"""Fix the OpenAI Codex provider's OAuth config for the custom JSON device flow.

The 1.1.0 seed pointed oauth_token_url at the *poll* endpoint
(.../deviceauth/token) and had no flavor marker, so 'Start OAuth' POSTed
RFC-8628 form data to a JSON-only endpoint -> the server's Pydantic
'body should be a dictionary' error. Set the flavor + the real token-exchange
URL. Provider xmlids are owned by the noupdate data file, so this ORM write is
the only way to update existing installs on -u.
"""
from odoo import api, SUPERUSER_ID

CODEX = {
    'oauth_flavor': 'openai_codex',
    'oauth_token_url': 'https://auth.openai.com/oauth/token',
    'oauth_device_authorization_url': 'https://auth.openai.com/api/accounts/deviceauth/usercode',
    'oauth_client_id': 'app_EMoamEEZ73f0CkXaXp7hrann',
    'auth_type': 'oauth_device_code',
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    prov = env['ai.provider'].search([('code', '=', 'openai-codex')], limit=1)
    if prov:
        prov.write(CODEX)
