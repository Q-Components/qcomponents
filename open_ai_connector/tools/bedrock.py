# -*- coding: utf-8 -*-
"""AWS Bedrock Converse transport (api_mode='bedrock_converse').

Uses boto3 (optional dependency). Handles the message/tool conversion to the
Converse / ConverseStream API. boto3 handles SigV4 signing via the session
passed in by auth.py.
"""
from __future__ import annotations

import json

from .transport_base import Transport, RequestContext, register_transport
from .types import NormalizedResponse, ToolCall, Usage, map_finish_reason
from .http_client import AiHttpError

_STOP = {
    'end_turn': 'stop', 'tool_use': 'tool_calls', 'max_tokens': 'length',
    'stop_sequence': 'stop', 'content_filtered': 'content_filter',
    'guardrail_intervened': 'content_filter',
}
_DEFAULT_MAX_TOKENS = 4096


def _content_to_converse(content):
    if content is None:
        return [{'text': ''}]
    if isinstance(content, str):
        return [{'text': content}] if content else [{'text': ''}]
    blocks = []
    for part in content:
        if isinstance(part, str):
            blocks.append({'text': part})
        elif isinstance(part, dict):
            if part.get('type') == 'text':
                blocks.append({'text': part.get('text', '')})
            elif part.get('type') == 'image_url':
                url = part.get('image_url')
                url = url.get('url') if isinstance(url, dict) else url
                if isinstance(url, str) and url.startswith('data:'):
                    try:
                        header, data = url.split(',', 1)
                        fmt = header.split('/')[1].split(';')[0]
                    except (ValueError, IndexError):
                        continue
                    import base64
                    blocks.append({'image': {'format': fmt,
                                             'source': {'bytes': base64.b64decode(data)}}})
    return blocks or [{'text': ''}]


def convert_messages_to_converse(messages):
    system = []
    out = []
    for m in messages or []:
        role = m.get('role')
        content = m.get('content')
        if role == 'system':
            txt = content if isinstance(content, str) else None
            if txt:
                system.append({'text': txt})
            continue
        if role == 'tool':
            out.append({'role': 'user', 'content': [{'toolResult': {
                'toolUseId': m.get('tool_call_id'),
                'content': [{'text': content if isinstance(content, str) else json.dumps(content)}],
            }}]})
            continue
        blocks = _content_to_converse(content)
        if role == 'assistant' and m.get('tool_calls'):
            for tc in m['tool_calls']:
                fn = tc.get('function') or {}
                try:
                    args = json.loads(fn.get('arguments') or '{}')
                except (ValueError, TypeError):
                    args = {}
                blocks.append({'toolUse': {'toolUseId': tc.get('id'),
                                           'name': fn.get('name'), 'input': args}})
        out.append({'role': 'assistant' if role == 'assistant' else 'user',
                    'content': blocks})
    return system, out


def convert_tools_to_converse(tools):
    out = []
    for t in tools or []:
        fn = t.get('function') or t
        out.append({'toolSpec': {
            'name': fn.get('name'), 'description': fn.get('description', ''),
            'inputSchema': {'json': fn.get('parameters') or {'type': 'object', 'properties': {}}},
        }})
    return out


@register_transport
class BedrockTransport(Transport):
    api_mode = 'bedrock_converse'

    def _client(self, ctx: RequestContext):
        session = ctx.boto3_session
        if session is None:
            raise AiHttpError(0, "boto3 session not resolved for Bedrock credential.")
        region = (ctx.extra.get('aws_region') or ctx.provider.get('aws_region')
                  or 'us-east-1')
        return session.client('bedrock-runtime', region_name=region)

    def build_body(self, ctx: RequestContext) -> dict:
        system, msgs = convert_messages_to_converse(ctx.messages)
        max_tokens = ctx.max_tokens or ctx.provider.get('default_max_tokens') or _DEFAULT_MAX_TOKENS
        kwargs = {'modelId': ctx.model, 'messages': msgs,
                  'inferenceConfig': {'maxTokens': max_tokens}}
        if system:
            kwargs['system'] = system
        if ctx.temperature is not None and not ctx.provider.get('omit_temperature'):
            kwargs['inferenceConfig']['temperature'] = ctx.temperature
        if ctx.tools:
            kwargs['toolConfig'] = {'tools': convert_tools_to_converse(ctx.tools)}
        return kwargs

    def complete(self, ctx: RequestContext) -> NormalizedResponse:
        client = self._client(ctx)
        resp = client.converse(**self.build_body(ctx))
        return self.parse_response(resp, ctx)

    def parse_response(self, raw: dict, ctx: RequestContext) -> NormalizedResponse:
        msg = (raw.get('output') or {}).get('message') or {}
        text_parts, tool_calls = [], []
        for block in msg.get('content') or []:
            if 'text' in block:
                text_parts.append(block['text'])
            elif 'toolUse' in block:
                tu = block['toolUse']
                tool_calls.append(ToolCall(id=tu.get('toolUseId'), name=tu.get('name', ''),
                                           arguments=json.dumps(tu.get('input') or {})))
        usage = None
        u = raw.get('usage')
        if u:
            usage = Usage(prompt_tokens=u.get('inputTokens') or 0,
                          completion_tokens=u.get('outputTokens') or 0,
                          total_tokens=u.get('totalTokens') or 0)
        return NormalizedResponse(
            content='\n'.join(text_parts) if text_parts else None,
            tool_calls=tool_calls or None,
            finish_reason=map_finish_reason(raw.get('stopReason'), _STOP), usage=usage)

    def stream(self, ctx: RequestContext):
        client = self._client(ctx)
        resp = client.converse_stream(**self.build_body(ctx))
        content_parts = []
        finish_reason = 'stop'
        usage = None
        for event in resp.get('stream', []):
            if 'contentBlockDelta' in event:
                delta = event['contentBlockDelta'].get('delta') or {}
                piece = delta.get('text')
                if piece:
                    content_parts.append(piece)
                    yield {'delta': piece}
            elif 'messageStop' in event:
                finish_reason = map_finish_reason(
                    event['messageStop'].get('stopReason'), _STOP)
            elif 'metadata' in event:
                u = event['metadata'].get('usage') or {}
                if u:
                    usage = {'prompt_tokens': u.get('inputTokens') or 0,
                             'completion_tokens': u.get('outputTokens') or 0,
                             'total_tokens': u.get('totalTokens') or 0}
        yield {'done': True, 'content': ''.join(content_parts),
               'finish_reason': finish_reason, 'tool_calls': None, 'usage': usage}
