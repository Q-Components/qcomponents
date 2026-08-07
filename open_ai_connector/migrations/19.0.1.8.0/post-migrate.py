# -*- coding: utf-8 -*-
"""Apply the curated provider display order on existing installs.

`sequence` lives on the noupdate=1 provider records (data/ai_provider_data.xml),
so a plain -u won't refresh it — set it here by code. Keep SEQUENCE_BY_CODE in
sync with the <field name="sequence"> values in that data file.

Most popular providers float to the top (lower = higher); the long tail shares
500 and sorts alphabetically; the unwired Copilot ACP sits last.
"""
from odoo import api, SUPERUSER_ID

SEQUENCE_BY_CODE = {
    # ── flagship ──
    'openai-codex': 10,
    'anthropic': 20,
    'gemini': 30,
    'xai': 40,
    'deepseek': 50,
    'openrouter': 60,
    # ── major ──
    'qwen-oauth': 70,
    'alibaba': 80,
    'zai': 90,
    'kimi-coding': 100,
    'minimax': 110,
    'nvidia': 120,
    'huggingface': 130,
    'bedrock': 140,
    'custom': 150,
    'ollama-cloud': 160,
    # ── common ──
    'copilot': 170,
    'google-gemini-cli': 180,
    'xai-oauth': 190,
    'novita': 200,
    # ── long tail (alphabetical via name) ──
    'alibaba-coding-plan': 500,
    'arcee': 500,
    'azure-foundry': 500,
    'gmi': 500,
    'kilocode': 500,
    'kimi-coding-cn': 500,
    'minimax-cn': 500,
    'minimax-oauth': 500,
    'opencode-zen': 500,
    'opencode-go': 500,
    'stepfun': 500,
    'xiaomi': 500,
    # ── unwired, last ──
    'copilot-acp': 900,
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Provider = env['ai.provider']
    for code, seq in SEQUENCE_BY_CODE.items():
        prov = Provider.search([('code', '=', code)], limit=1)
        if prov:
            prov.sequence = seq
