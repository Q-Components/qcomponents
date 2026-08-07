# -*- coding: utf-8 -*-
"""Give the OpenAI Codex provider a working models endpoint + curated fallback.

Codex has no public /models listing; the ChatGPT backend exposes one at
chatgpt.com/backend-api/codex/models (shape {"models":[{"slug":..}]}). Without
models_url + fallback_models, "Fetch Models" returned 0. The provider xmlid is
owned by the noupdate data file, so set these via ORM for existing installs.
"""
from odoo import api, SUPERUSER_ID

MODELS_URL = 'https://chatgpt.com/backend-api/codex/models?client_version=1.0.0'
FALLBACK = '\n'.join([
    'gpt-5.5', 'gpt-5.4-mini', 'gpt-5.4', 'gpt-5.3-codex', 'gpt-5.3-codex-spark',
])


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    prov = env['ai.provider'].search([('code', '=', 'openai-codex')], limit=1)
    if not prov:
        return
    vals = {}
    if not prov.models_url:
        vals['models_url'] = MODELS_URL
    if not prov.fallback_models:
        vals['fallback_models'] = FALLBACK
    if vals:
        prov.write(vals)
