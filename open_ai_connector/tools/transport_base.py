# -*- coding: utf-8 -*-
"""Transport ABC + api_mode -> transport registry.

A transport owns the data path for one ``api_mode``:
    build_body -> send -> parse_response   (+ optional streaming)

It does NOT own credential resolution (see auth.py) — the resolved auth
(headers, base_url, proxy, boto3 session) is handed in via RequestContext.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from . import http_client
from .types import NormalizedResponse
from .utils import join_url

_logger = logging.getLogger(__name__)


@dataclass
class RequestContext:
    """Everything a transport needs to make one inference call."""
    model: str
    messages: list
    tools: list | None = None
    tool_choice: object | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = False
    extra: dict = field(default_factory=dict)        # provider-specific knobs
    # Provider declarative config (plain dict, decoupled from the ORM record):
    provider: dict = field(default_factory=dict)
    # Resolved auth (from auth.resolve):
    headers: dict = field(default_factory=dict)
    base_url: str = ''
    proxy_url: str | None = None
    boto3_session: object | None = None
    timeout: float = 120.0


class Transport(ABC):
    """Base class for provider-protocol format conversion + I/O."""

    api_mode: str = ''
    # Path appended to base_url for this protocol (override per transport).
    url_path: str = '/chat/completions'

    @abstractmethod
    def build_body(self, ctx: RequestContext) -> dict:
        """Build the JSON request body (provider-native shape)."""

    @abstractmethod
    def parse_response(self, raw: dict, ctx: RequestContext) -> NormalizedResponse:
        """Parse a non-streaming raw response into a NormalizedResponse."""

    # ── default HTTP implementations (overridden by bedrock) ───────────
    def endpoint(self, ctx: RequestContext) -> str:
        base = ctx.base_url or ctx.provider.get('base_url') or ''
        return join_url(base, self.url_path)

    def complete(self, ctx: RequestContext) -> NormalizedResponse:
        body = self.build_body(ctx)
        raw = http_client.post_json(
            self.endpoint(ctx), headers=ctx.headers, json_body=body,
            timeout=ctx.timeout, proxy_url=ctx.proxy_url,
        )
        return self.parse_response(raw, ctx)

    def stream(self, ctx: RequestContext):
        """Yield streamed chunks. Default: emulate via a single complete() call.

        Concrete HTTP transports override this with a true SSE generator.
        Chunk shape: ``{'delta': str}`` for text, then a terminal
        ``{'done': True, 'content': str, 'finish_reason': str, 'usage': dict|None}``.
        """
        nr = self.complete(ctx)
        if nr.content:
            yield {'delta': nr.content}
        yield {
            'done': True,
            'content': nr.content or '',
            'finish_reason': nr.finish_reason,
            'tool_calls': [tc.to_dict() for tc in nr.tool_calls] if nr.tool_calls else None,
            'usage': nr.usage.to_dict() if nr.usage else None,
        }


# ── registry ───────────────────────────────────────────────────────────
_REGISTRY: dict = {}
_discovered = False


def register_transport(cls):
    inst = cls()
    _REGISTRY[inst.api_mode] = inst
    return cls


def get_transport(api_mode: str) -> Transport | None:
    # Use a discovery flag (not `if not _REGISTRY`): a single transport module
    # may already be imported elsewhere, leaving the registry partially filled.
    global _discovered
    if not _discovered:
        _discover()
    return _REGISTRY.get(api_mode)


def _discover():
    global _discovered
    _discovered = True
    # Import the concrete transports so they self-register.
    from . import chat_completions  # noqa: F401
    from . import anthropic  # noqa: F401
    from . import codex_responses  # noqa: F401
    from . import bedrock  # noqa: F401
    from . import gemini_cloudcode  # noqa: F401
