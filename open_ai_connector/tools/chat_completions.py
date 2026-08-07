# -*- coding: utf-8 -*-
"""OpenAI Chat Completions transport (api_mode='chat_completions').

The default/most common protocol — used by ~25 providers. Messages and tools
are already in OpenAI format (identity); we only shape temperature, the
max-tokens parameter name, streaming and provider quirks.
"""
from __future__ import annotations

from . import http_client, quirks
from .transport_base import Transport, RequestContext, register_transport
from .types import NormalizedResponse, ToolCall, Usage, map_finish_reason
from .utils import model_forces_max_completion_tokens

_FINISH = {
    'stop': 'stop', 'length': 'length', 'tool_calls': 'tool_calls',
    'function_call': 'tool_calls', 'content_filter': 'content_filter',
}


@register_transport
class ChatCompletionsTransport(Transport):
    api_mode = 'chat_completions'
    url_path = '/chat/completions'

    def build_body(self, ctx: RequestContext) -> dict:
        code = ctx.provider.get('code')
        messages = quirks.prepare_messages(code, ctx.messages)
        body = {'model': ctx.model, 'messages': messages}

        if ctx.tools:
            body['tools'] = ctx.tools
            if ctx.tool_choice is not None:
                body['tool_choice'] = ctx.tool_choice

        # Temperature: provider may force-omit or fix it.
        if not ctx.provider.get('omit_temperature'):
            fixed = ctx.provider.get('fixed_temperature')
            if fixed:
                body['temperature'] = fixed
            elif ctx.temperature is not None:
                body['temperature'] = ctx.temperature

        # Max tokens — name varies by model family.
        max_tokens = ctx.max_tokens or ctx.provider.get('default_max_tokens') or None
        if max_tokens:
            key = ('max_completion_tokens'
                   if model_forces_max_completion_tokens(ctx.model) else 'max_tokens')
            body[key] = max_tokens

        if ctx.stream:
            body['stream'] = True
            body['stream_options'] = {'include_usage': True}

        # Provider quirks (reasoning/thinking) + caller extra_body.
        extra_body, top_level, _hdrs = quirks.build_extras(
            code, ctx.model, ctx.extra.get('reasoning'), ctx.extra)
        eb = dict(extra_body)
        eb.update(ctx.extra.get('extra_body') or {})
        if eb:
            # OpenAI-compat: extra_body fields are sent at the top level of the body.
            body.update(eb)
        body.update(top_level)
        return body

    def _stream_headers(self, ctx):
        headers = dict(ctx.headers)
        _eb, _tl, extra_headers = quirks.build_extras(
            ctx.provider.get('code'), ctx.model, ctx.extra.get('reasoning'), ctx.extra)
        headers.update(extra_headers)
        headers.update(ctx.extra.get('extra_headers') or {})
        return headers

    def complete(self, ctx: RequestContext) -> NormalizedResponse:
        body = self.build_body(ctx)
        raw = http_client.post_json(
            self.endpoint(ctx), headers=self._stream_headers(ctx),
            json_body=body, timeout=ctx.timeout, proxy_url=ctx.proxy_url)
        return self.parse_response(raw, ctx)

    def parse_response(self, raw: dict, ctx: RequestContext) -> NormalizedResponse:
        choices = raw.get('choices') or [{}]
        choice = choices[0] or {}
        msg = choice.get('message') or {}
        content = msg.get('content')
        # Some providers return content as a list of parts.
        if isinstance(content, list):
            content = ''.join(
                p.get('text', '') for p in content if isinstance(p, dict))

        tool_calls = None
        raw_tcs = msg.get('tool_calls')
        if raw_tcs:
            tool_calls = []
            for tc in raw_tcs:
                fn = tc.get('function') or {}
                tool_calls.append(ToolCall(
                    id=tc.get('id'),
                    name=fn.get('name', ''),
                    arguments=fn.get('arguments', '{}'),
                ))

        usage = None
        u = raw.get('usage')
        if u:
            usage = Usage(
                prompt_tokens=u.get('prompt_tokens') or 0,
                completion_tokens=u.get('completion_tokens') or 0,
                total_tokens=u.get('total_tokens') or 0,
                cached_tokens=(u.get('prompt_tokens_details') or {}).get('cached_tokens', 0),
            )

        reasoning = msg.get('reasoning') or msg.get('reasoning_content')
        finish = map_finish_reason(choice.get('finish_reason'), _FINISH)
        return NormalizedResponse(
            content=content, tool_calls=tool_calls, finish_reason=finish,
            reasoning=reasoning, usage=usage)

    def stream(self, ctx: RequestContext):
        body = self.build_body(ctx)
        body['stream'] = True
        body.setdefault('stream_options', {'include_usage': True})
        content_parts = []
        tool_acc = {}          # index -> {'id','name','arguments'}
        finish_reason = 'stop'
        usage = None
        for event in http_client.post_sse(
                self.endpoint(ctx), headers=self._stream_headers(ctx),
                json_body=body, timeout=max(ctx.timeout, 600.0), proxy_url=ctx.proxy_url):
            if event.get('usage'):
                u = event['usage']
                usage = {
                    'prompt_tokens': u.get('prompt_tokens') or 0,
                    'completion_tokens': u.get('completion_tokens') or 0,
                    'total_tokens': u.get('total_tokens') or 0,
                }
            for choice in event.get('choices') or []:
                delta = choice.get('delta') or {}
                piece = delta.get('content')
                if piece:
                    content_parts.append(piece)
                    yield {'delta': piece}
                for tc in delta.get('tool_calls') or []:
                    idx = tc.get('index', 0)
                    slot = tool_acc.setdefault(idx, {'id': None, 'name': '', 'arguments': ''})
                    if tc.get('id'):
                        slot['id'] = tc['id']
                    fn = tc.get('function') or {}
                    if fn.get('name'):
                        slot['name'] = fn['name']
                    if fn.get('arguments'):
                        slot['arguments'] += fn['arguments']
                if choice.get('finish_reason'):
                    finish_reason = map_finish_reason(choice['finish_reason'], _FINISH)
        tool_calls = None
        if tool_acc:
            tool_calls = [{
                'id': v['id'], 'type': 'function',
                'function': {'name': v['name'], 'arguments': v['arguments']},
            } for _, v in sorted(tool_acc.items())]
        yield {
            'done': True,
            'content': ''.join(content_parts),
            'finish_reason': finish_reason,
            'tool_calls': tool_calls,
            'usage': usage,
        }
