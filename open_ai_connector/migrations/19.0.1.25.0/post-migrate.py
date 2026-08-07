# -*- coding: utf-8 -*-
"""Superseded — no-op.

This version briefly disabled OpenAI-Codex image generation on the assumption the
backend always strips the image_generation tool. That was wrong: it's PLAN-GATED
(Team/Pro/paid plans support it; Free/Plus strip it). The 19.0.1.26.0 migration
re-enables the capability flag. Kept as a no-op so the upgrade chain is intact.
"""


def migrate(cr, version):
    pass
