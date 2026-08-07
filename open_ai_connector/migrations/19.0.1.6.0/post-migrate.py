# -*- coding: utf-8 -*-
"""Drop the 'nous' provider (removed from the catalog) on existing installs.

The provider record is no longer in the data files, so a fresh install never
creates it; this removes it (and any credentials/models via ondelete=cascade)
from databases that already had it. Odoo's orphan cleanup usually handles this,
but we delete explicitly so it's deterministic.
"""
from odoo import api, SUPERUSER_ID

XAI_OAUTH = {
    'oauth_client_id': 'b1a00492-073a-47ea-816f-4c329264a828',
    'oauth_auth_url': 'https://auth.x.ai/oauth2/authorize',
    'oauth_token_url': 'https://auth.x.ai/oauth2/token',
    'oauth_scopes': 'openid profile email offline_access grok-cli:access api:access',
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    nous = env['ai.provider'].search([('code', '=', 'nous')])
    if nous:
        nous.unlink()
    # The xai-oauth record is created by the noupdate=1 data file on -u, so the
    # separate oauth-endpoints data file can't set its endpoints (only fresh -i
    # does). ORM-write them here for existing installs.
    xo = env['ai.provider'].search([('code', '=', 'xai-oauth')], limit=1)
    if xo:
        xo.write({k: v for k, v in XAI_OAUTH.items() if not xo[k]})
