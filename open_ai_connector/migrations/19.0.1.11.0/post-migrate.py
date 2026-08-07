# -*- coding: utf-8 -*-
"""Seed Google Gemini CLI fallback models on existing installs.

google-gemini-cli talks to Cloud Code Assist (base_url ``cloudcode-pa://google``)
which has no public /models endpoint, so a live fetch returns nothing. The
provider record is owned by the noupdate=1 data file, so set its curated
fallback models (+ aux model) here for installs upgrading from < 19.0.1.11.0,
and pre-populate ai.model so the catalog is ready without a manual re-fetch.
"""
from odoo import api, SUPERUSER_ID

GEMINI_CLI_MODELS = [
    'gemini-3.1-pro-preview',
    'gemini-3-pro-preview',
    'gemini-3-flash-preview',
    'gemini-3.5-flash',
]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    prov = env['ai.provider'].search([('code', '=', 'google-gemini-cli')], limit=1)
    if not prov:
        return
    vals = {}
    if not prov.fallback_models:
        vals['fallback_models'] = '\n'.join(GEMINI_CLI_MODELS)
    if not prov.default_aux_model:
        vals['default_aux_model'] = 'gemini-3-flash-preview'
    if vals:
        prov.write(vals)
    # Pre-populate the catalog so the connected credential has models immediately.
    env['ai.model']._upsert(prov, GEMINI_CLI_MODELS)
