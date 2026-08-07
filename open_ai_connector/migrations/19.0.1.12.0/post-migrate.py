# -*- coding: utf-8 -*-
"""Wire Google Gemini CLI chat through the Cloud Code Assist transport.

Until 19.0.1.12.0 the ``google-gemini-cli`` provider reported
api_mode='chat_completions' (the field default), so chat() routed it to the
OpenAI transport, which built ``cloudcode-pa://google/chat/completions`` — an
unsupported URL scheme the SSRF guard (correctly) blocked. Chat now has a
dedicated ``gemini_cloudcode`` transport that speaks Google's Code Assist
v1internal protocol.

The provider record is owned by the noupdate=1 data file, so flip its api_mode
here for installs upgrading from < 19.0.1.12.0. Writing via the ORM also
recomputes the stored ``is_wired`` flag.
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    prov = env['ai.provider'].search([('code', '=', 'google-gemini-cli')], limit=1)
    if prov and prov.api_mode != 'gemini_cloudcode':
        prov.write({'api_mode': 'gemini_cloudcode'})
