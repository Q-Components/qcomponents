# -*- coding: utf-8 -*-
"""Keep OpenAI-Codex image generation enabled (plan-gated, works on Team/Pro/paid).

Confirmed live: a Team-plan Codex credential generates images via the /responses
image_generation tool; Free/Plus plans strip it (the call 400s with a clear
message). So the capability stays ON — users select a paid Codex credential.
"""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE ai_provider
           SET supports_image_gen = TRUE,
               default_image_model = COALESCE(NULLIF(default_image_model, ''), 'gpt-image-2-medium')
         WHERE code = 'openai-codex'
        """
    )
