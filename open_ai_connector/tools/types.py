# -*- coding: utf-8 -*-
"""Shared normalized response types.

The canonical shape that every transport normalizes responses to — the
cross-provider surface every caller reads.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class ToolCall:
    """A normalized tool/function call from any provider."""
    id: str | None
    name: str
    arguments: str  # JSON string
    provider_data: dict | None = field(default=None)

    def to_dict(self) -> dict:
        d = {'id': self.id, 'type': 'function',
             'function': {'name': self.name, 'arguments': self.arguments}}
        if self.provider_data:
            d['provider_data'] = self.provider_data
        return d

    def parsed_arguments(self) -> Any:
        try:
            return json.loads(self.arguments)
        except (ValueError, TypeError):
            return {}


@dataclass
class Usage:
    """Token usage from an API response."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NormalizedResponse:
    """Normalized API response from any provider."""
    content: str | None
    tool_calls: list[ToolCall] | None
    finish_reason: str  # "stop" | "tool_calls" | "length" | "content_filter"
    reasoning: str | None = None
    usage: Usage | None = None
    provider_data: dict | None = field(default=None)

    def to_dict(self) -> dict:
        return {
            'content': self.content,
            'tool_calls': [tc.to_dict() for tc in self.tool_calls] if self.tool_calls else None,
            'finish_reason': self.finish_reason,
            'reasoning': self.reasoning,
            'usage': self.usage.to_dict() if self.usage else None,
            'provider_data': self.provider_data,
        }


def map_finish_reason(reason: str | None, mapping: dict) -> str:
    """Translate a provider stop reason to the normalized set; default 'stop'."""
    if reason is None:
        return 'stop'
    return mapping.get(reason, 'stop')
