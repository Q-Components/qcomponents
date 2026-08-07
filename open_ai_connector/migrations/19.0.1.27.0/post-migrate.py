# -*- coding: utf-8 -*-
"""Enable image-edit (remix) on the Codex provider for already-installed DBs.

noupdate data isn't reapplied on -u, and this flag is new, so set it directly.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        "UPDATE ai_provider SET supports_image_edit = TRUE WHERE code = 'openai-codex'")
    _logger.info("open_ai_connector 19.0.1.27.0: set supports_image_edit on openai-codex")
