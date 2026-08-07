# -*- coding: utf-8 -*-
"""Seed the loopback redirect_uri + extra authorize params for the PKCE
paste-back OAuth providers (xAI Grok, Google Gemini CLI) on existing installs.

These fields live in the noupdate=1-owned provider records, so the data file
can't set them on -u; ORM-write them here.
"""
from odoo import api, SUPERUSER_ID

PROVIDER_VALS = {
    'xai-oauth': {
        'oauth_redirect_uri': 'http://127.0.0.1:56121/callback',
        'oauth_extra_authorize_params': '{"plan": "generic"}',
    },
    'google-gemini-cli': {
        'oauth_redirect_uri': 'http://127.0.0.1:8085/oauth2callback',
        'oauth_extra_authorize_params': '{"access_type": "offline", "prompt": "consent"}',
    },
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Provider = env['ai.provider']
    for code, vals in PROVIDER_VALS.items():
        prov = Provider.search([('code', '=', code)], limit=1)
        if prov:
            prov.write({k: v for k, v in vals.items() if not prov[k]})
