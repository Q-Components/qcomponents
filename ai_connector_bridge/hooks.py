# -*- coding: utf-8 -*-
"""post_load hook: monkeypatch Odoo AI's single LLM-call seam to (optionally)
route through the AI Connector.

We wrap ``LLMApiService._request_llm`` — the one method Odoo's tool-call loop
(``_request_llm_silent``) calls per turn. When routing is active we call
``ai.connector.chat()`` and return Odoo's exact ``(response, to_call,
next_inputs)`` 3-tuple, so the loop, tool execution and termination all keep
working unchanged. When routing is off we delegate to the original method, so
stock Odoo AI behaviour is untouched. The patch is process-wide (applied once),
but the per-database toggle is read at call time, so each DB decides on its own.
"""
import logging

_logger = logging.getLogger(__name__)


def _patch_llm_api_service():
    try:
        from odoo.addons.ai.utils.llm_api_service import LLMApiService
    except Exception:  # noqa: BLE001 - ai module not importable -> bridge inert
        _logger.warning("ai_connector_bridge: odoo.addons.ai not importable; bridge inactive")
        return
    if getattr(LLMApiService, '_oconn_patched', False):
        return

    from .utils import bridge

    LLMApiService._oconn_orig_request_llm = LLMApiService._request_llm

    def _request_llm(self, *args, **kwargs):
        llm_model = kwargs.get('llm_model') or (args[0] if args else None)
        try:
            target = bridge.route(self.env, llm_model)
        except Exception:  # noqa: BLE001 - never break stock AI on a routing error
            _logger.exception("ai_connector_bridge: routing failed; using stock provider")
            target = None
        if not target:
            return self._oconn_orig_request_llm(*args, **kwargs)
        # Keep OpenAI loop semantics so _build_tool_call_response / next_inputs
        # round-trip (the loop branches on self.provider).
        self.provider = 'openai'
        return bridge.request_via_connector(
            self, target[0], target[1], *args, credential_id=target[2], **kwargs)

    LLMApiService._request_llm = _request_llm
    LLMApiService._oconn_patched = True
    _logger.info("ai_connector_bridge: patched LLMApiService._request_llm")
