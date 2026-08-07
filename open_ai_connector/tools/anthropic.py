# -*- coding: utf-8 -*-
"""Anthropic Messages transport (api_mode='anthropic_messages').

Handles the message/tool/vision conversion and content-block parsing. Auth
(x-api-key + anthropic-version) is attached by auth.py; this transport owns
the /v1/messages body and response shape.
"""
from __future__ import annotations

import hashlib
import json
import uuid

from . import http_client
from .transport_base import Transport, RequestContext, register_transport
from .types import NormalizedResponse, ToolCall, Usage, map_finish_reason

# Anthropic scopes claude.ai OAuth tokens to Claude Code and REQUIRES the system
# prompt to begin with this exact identity block — otherwise /v1/messages refuses
# the token.
CLAUDE_CODE_IDENTITY = "You are Claude Code, Anthropic's official CLI for Claude."

_STOP = {
    'end_turn': 'stop', 'tool_use': 'tool_calls', 'max_tokens': 'length',
    'stop_sequence': 'stop', 'refusal': 'content_filter',
    'model_context_window_exceeded': 'length',
}
_DEFAULT_MAX_TOKENS = 16384


def _image_block(url):
    """Convert an OpenAI image_url value to an Anthropic image block."""
    if isinstance(url, dict):
        url = url.get('url', '')
    url = url or ''
    if url.startswith('data:'):
        # data:<media_type>;base64,<data>
        try:
            header, data = url.split(',', 1)
            media_type = header.split(';')[0][len('data:'):] or 'image/png'
        except ValueError:
            return None
        return {'type': 'image',
                'source': {'type': 'base64', 'media_type': media_type, 'data': data}}
    return {'type': 'image', 'source': {'type': 'url', 'url': url}}


def _content_to_blocks(content):
    if content is None:
        return []
    if isinstance(content, str):
        return [{'type': 'text', 'text': content}] if content else []
    blocks = []
    for part in content:
        if isinstance(part, str):
            blocks.append({'type': 'text', 'text': part})
        elif isinstance(part, dict):
            ptype = part.get('type')
            if ptype == 'text':
                blocks.append({'type': 'text', 'text': part.get('text', '')})
            elif ptype == 'image_url':
                blk = _image_block(part.get('image_url'))
                if blk:
                    blocks.append(blk)
            else:
                blocks.append(part)
    return blocks


def convert_messages_to_anthropic(messages):
    """Return (system, anthropic_messages)."""
    system_parts = []
    out = []
    for m in messages or []:
        role = m.get('role')
        content = m.get('content')
        if role == 'system':
            if isinstance(content, str):
                system_parts.append(content)
            elif isinstance(content, list):
                for p in content:
                    if isinstance(p, dict) and p.get('type') == 'text':
                        system_parts.append(p.get('text', ''))
                    elif isinstance(p, str):
                        system_parts.append(p)
            continue
        if role == 'tool':
            out.append({'role': 'user', 'content': [{
                'type': 'tool_result',
                'tool_use_id': m.get('tool_call_id'),
                'content': content if isinstance(content, str) else _content_to_blocks(content),
            }]})
            continue
        blocks = _content_to_blocks(content)
        if role == 'assistant' and m.get('tool_calls'):
            for tc in m['tool_calls']:
                fn = tc.get('function') or {}
                try:
                    args = json.loads(fn.get('arguments') or '{}')
                except (ValueError, TypeError):
                    args = {}
                blocks.append({'type': 'tool_use', 'id': tc.get('id'),
                               'name': fn.get('name'), 'input': args})
        out.append({'role': 'assistant' if role == 'assistant' else 'user',
                    'content': blocks})
    system = '\n\n'.join([s for s in system_parts if s]) if system_parts else None
    return system, out


def convert_tools_to_anthropic(tools):
    result = []
    for t in tools or []:
        fn = t.get('function') or t
        result.append({
            'name': fn.get('name', ''),
            'description': fn.get('description', ''),
            'input_schema': fn.get('parameters') or {'type': 'object', 'properties': {}},
        })
    return result


@register_transport
class AnthropicTransport(Transport):
    api_mode = 'anthropic_messages'
    url_path = '/v1/messages'

    def _oauth_mode(self, ctx: RequestContext) -> bool:
        """True ONLY for real claude.ai OAuth (Claude Code) — needs the full
        signature (system-prompt prefix + uTLS). Other anthropic-protocol OAuth
        providers (MiniMax /anthropic) are excluded: they'd break with the
        Claude Code identity block and don't sit behind Anthropic's Cloudflare."""
        return (ctx.provider.get('auth_type') in ('oauth_external', 'oauth_device_code')
                and ctx.provider.get('oauth_flavor') == 'anthropic')

    def _request_headers(self, ctx: RequestContext) -> dict:
        headers = dict(ctx.headers)
        if self._oauth_mode(ctx):
            token = (headers.get('Authorization') or '')[len('Bearer '):]
            if token:
                # Stable per-credential session id, like Claude Code's.
                headers.setdefault('X-Claude-Code-Session-Id',
                                   hashlib.sha256(token.encode()).hexdigest()[:32])
            headers['x-client-request-id'] = str(uuid.uuid4())
        return headers

    def _impersonate(self, ctx: RequestContext):
        return 'chrome' if self._oauth_mode(ctx) else None

    def build_body(self, ctx: RequestContext) -> dict:
        system, amsgs = convert_messages_to_anthropic(ctx.messages)
        max_tokens = ctx.max_tokens or ctx.provider.get('default_max_tokens') or _DEFAULT_MAX_TOKENS
        body = {'model': ctx.model, 'messages': amsgs, 'max_tokens': max_tokens}
        if self._oauth_mode(ctx):
            # Prefix the Claude Code identity as the first system block (required
            # by Anthropic for OAuth-scoped tokens); keep the caller's system next.
            blocks = [{'type': 'text', 'text': CLAUDE_CODE_IDENTITY}]
            if system:
                blocks.append({'type': 'text', 'text': system})
            body['system'] = blocks
        elif system:
            body['system'] = system
        if ctx.tools:
            body['tools'] = convert_tools_to_anthropic(ctx.tools)
            tc = ctx.tool_choice
            if tc in (None, 'auto'):
                body['tool_choice'] = {'type': 'auto'}
            elif tc == 'required':
                body['tool_choice'] = {'type': 'any'}
            elif isinstance(tc, str):
                body['tool_choice'] = {'type': 'tool', 'name': tc}
        if not ctx.provider.get('omit_temperature') and ctx.temperature is not None:
            body['temperature'] = ctx.temperature
        reasoning = ctx.extra.get('reasoning')
        if isinstance(reasoning, dict) and reasoning.get('enabled') is not False:
            effort = (reasoning.get('effort') or 'medium').strip().lower()
            budget = {'low': 2048, 'medium': 8192, 'high': 16384,
                      'xhigh': 24576, 'max': 32000}.get(effort, 8192)
            body['thinking'] = {'type': 'enabled', 'budget_tokens': budget}
        if ctx.stream:
            body['stream'] = True
        body.update(ctx.extra.get('extra_body') or {})
        return body

    def complete(self, ctx: RequestContext) -> NormalizedResponse:
        body = self.build_body(ctx)
        raw = http_client.post_json(
            self.endpoint(ctx), headers=self._request_headers(ctx), json_body=body,
            timeout=ctx.timeout, proxy_url=ctx.proxy_url, impersonate=self._impersonate(ctx))
        return self.parse_response(raw, ctx)

    def parse_response(self, raw: dict, ctx: RequestContext) -> NormalizedResponse:
        text_parts, reasoning_parts, tool_calls = [], [], []
        for block in raw.get('content') or []:
            btype = block.get('type')
            if btype == 'text':
                text_parts.append(block.get('text', ''))
            elif btype in ('thinking', 'redacted_thinking'):
                reasoning_parts.append(block.get('thinking') or block.get('data') or '')
            elif btype == 'tool_use':
                tool_calls.append(ToolCall(
                    id=block.get('id'), name=block.get('name', ''),
                    arguments=json.dumps(block.get('input') or {})))
        usage = None
        u = raw.get('usage')
        if u:
            pt = u.get('input_tokens') or 0
            ct = u.get('output_tokens') or 0
            usage = Usage(prompt_tokens=pt, completion_tokens=ct,
                          total_tokens=pt + ct,
                          cached_tokens=u.get('cache_read_input_tokens') or 0)
        return NormalizedResponse(
            content='\n'.join(text_parts) if text_parts else None,
            tool_calls=tool_calls or None,
            finish_reason=map_finish_reason(raw.get('stop_reason'), _STOP),
            reasoning='\n\n'.join(reasoning_parts) if reasoning_parts else None,
            usage=usage)

    def stream(self, ctx: RequestContext):
        body = self.build_body(ctx)
        body['stream'] = True
        content_parts = []
        tool_blocks = {}        # index -> {'id','name','arguments'}
        finish_reason = 'stop'
        prompt_tokens = completion_tokens = 0
        for ev in http_client.post_sse(
                self.endpoint(ctx), headers=self._request_headers(ctx), json_body=body,
                timeout=max(ctx.timeout, 600.0), proxy_url=ctx.proxy_url,
                impersonate=self._impersonate(ctx)):
            etype = ev.get('type')
            if etype == 'message_start':
                u = (ev.get('message') or {}).get('usage') or {}
                prompt_tokens = u.get('input_tokens') or 0
            elif etype == 'content_block_start':
                blk = ev.get('content_block') or {}
                if blk.get('type') == 'tool_use':
                    tool_blocks[ev.get('index', 0)] = {
                        'id': blk.get('id'), 'name': blk.get('name', ''), 'arguments': ''}
            elif etype == 'content_block_delta':
                delta = ev.get('delta') or {}
                if delta.get('type') == 'text_delta':
                    piece = delta.get('text', '')
                    if piece:
                        content_parts.append(piece)
                        yield {'delta': piece}
                elif delta.get('type') == 'input_json_delta':
                    slot = tool_blocks.get(ev.get('index', 0))
                    if slot is not None:
                        slot['arguments'] += delta.get('partial_json', '')
            elif etype == 'message_delta':
                d = ev.get('delta') or {}
                if d.get('stop_reason'):
                    finish_reason = map_finish_reason(d['stop_reason'], _STOP)
                u = ev.get('usage') or {}
                completion_tokens = u.get('output_tokens') or completion_tokens
        tool_calls = None
        if tool_blocks:
            tool_calls = [{
                'id': v['id'], 'type': 'function',
                'function': {'name': v['name'], 'arguments': v['arguments'] or '{}'},
            } for _, v in sorted(tool_blocks.items())]
        yield {
            'done': True,
            'content': ''.join(content_parts),
            'finish_reason': finish_reason,
            'tool_calls': tool_calls,
            'usage': {'prompt_tokens': prompt_tokens,
                      'completion_tokens': completion_tokens,
                      'total_tokens': prompt_tokens + completion_tokens},
        }
