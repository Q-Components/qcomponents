# -*- coding: utf-8 -*-
"""Seed image/video generation capability flags on existing installs.

The provider base records live in the noupdate=1 data file, so new fields aren't
applied on -u — set them here. xAI (api-key + OAuth) does image AND video via
grok-imagine-*; OpenAI Codex does image (gpt-image-2 via the /responses tool) on
the ChatGPT OAuth alone.
"""

_CAPS = {
    'xai': dict(img=True, vid=True, im='grok-imagine-image', vm='grok-imagine-video'),
    'xai-oauth': dict(img=True, vid=True, im='grok-imagine-image', vm='grok-imagine-video'),
    # Codex image gen is gated OFF by the live ChatGPT Codex backend (it strips
    # the image_generation tool); flag stays False so the Playground doesn't
    # offer a dead end. The code path exists if it's ever enabled.
    'openai-codex': dict(img=False, vid=False, im='gpt-image-2-medium', vm=None),
}


def migrate(cr, version):
    for code, c in _CAPS.items():
        cr.execute(
            """
            UPDATE ai_provider
               SET supports_image_gen = %s,
                   supports_video_gen = %s,
                   default_image_model = %s,
                   default_video_model = %s
             WHERE code = %s
            """,
            (c['img'], c['vid'], c['im'], c['vm'], code),
        )
