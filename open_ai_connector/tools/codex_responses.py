# -*- coding: utf-8 -*-
"""OpenAI Responses transport (api_mode='codex_responses').

Used by openai-codex and xAI Grok. Implements the request/response shaping for
the synchronous /responses path. Focused on the chat + tool-call surface
(encrypted-reasoning replay is out of scope here).
"""
from __future__ import annotations

import base64
import json
import logging

from . import http_client
from .transport_base import Transport, RequestContext, register_transport
from .types import NormalizedResponse, ToolCall, Usage

_logger = logging.getLogger(__name__)

# The OpenAI /responses (Codex) backend REQUIRES a non-empty ``instructions``
# field (HTTP 400 "Instructions are required" otherwise). When the caller sends
# no system message we fall back to this default identity.
DEFAULT_INSTRUCTIONS = "You are a helpful AI assistant."


def _chatgpt_account_id(access_token):
    """Extract ``chatgpt_account_id`` from the OAuth access-token JWT.

    The claim lives at ``["https://api.openai.com/auth"]["chatgpt_account_id"]``
    (codex-rs auth.rs). The token is decoded without signature verification —
    the upstream already validated it; we only read a claim. Malformed tokens
    return '' so a bad token surfaces as a 401, not a crash.
    """
    if not isinstance(access_token, str) or access_token.count('.') < 2:
        return ''
    try:
        payload_b64 = access_token.split('.')[1]
        payload_b64 += '=' * (-len(payload_b64) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload_b64))
        acct = (claims.get('https://api.openai.com/auth') or {}).get('chatgpt_account_id')
        return acct if isinstance(acct, str) else ''
    except Exception:  # noqa: BLE001 - tolerate any malformed token
        return ''


def _codex_cloudflare_headers(authorization):
    """Headers the ChatGPT Codex backend's Cloudflare layer requires.

    It whitelists first-party originators (``codex_cli_rs``, ``codex_vscode``,
    …); requests from non-residential IPs (a server like Odoo) WITHOUT an
    allowed ``originator`` + matching User-Agent get a 403 ``cf-mitigated:
    challenge`` regardless of auth correctness. Pin codex_cli_rs to match the
    upstream CLI, and add ``ChatGPT-Account-ID`` from the token JWT.
    """
    headers = {
        'User-Agent': 'codex_cli_rs/0.0.0 (Odoo AI Connector)',
        'originator': 'codex_cli_rs',
    }
    token = authorization[len('Bearer '):] if authorization.startswith('Bearer ') else ''
    acct = _chatgpt_account_id(token)
    if acct:
        headers['ChatGPT-Account-ID'] = acct
    return headers


def _messages_to_input(messages):
    """Split out system->instructions, convert the rest to Responses input items.

    Handles the tool round-trip so multi-round tool loops work the same as on the
    chat/completions providers: an assistant turn carrying ``tool_calls`` becomes
    ``function_call`` items and an OpenAI-format ``role:'tool'`` result becomes a
    ``function_call_output`` item (the shapes the /responses API expects). Because
    we send ``store: False``, the prior ``function_call`` items must be echoed back
    in the input for their outputs to resolve.
    """
    instructions = ''
    items = []
    for m in messages or []:
        role = m.get('role')
        content = m.get('content')
        if role == 'system' and not instructions:
            instructions = content if isinstance(content, str) else _flatten_text(content)
            continue
        if role == 'tool':
            items.append({
                'type': 'function_call_output',
                'call_id': m.get('tool_call_id') or m.get('call_id') or '',
                'output': content if isinstance(content, str) else _flatten_text(content),
            })
            continue
        tool_calls = m.get('tool_calls') if role == 'assistant' else None
        if tool_calls:
            if content:
                items.append({'role': role, 'content': _to_input_content(role, content)})
            for tc in tool_calls:
                fn = tc.get('function') or {}
                call_id = (tc.get('provider_data') or {}).get('call_id') or tc.get('id') or ''
                items.append({
                    'type': 'function_call',
                    'call_id': call_id,
                    'name': fn.get('name', ''),
                    'arguments': fn.get('arguments') or '{}',
                })
            continue
        items.append({'role': role, 'content': _to_input_content(role, content)})
    return instructions, items


def _tool_calls_from_dicts(items):
    """Rebuild ToolCall objects from a streamed ``done`` chunk's dict form."""
    out = []
    for it in items or []:
        fn = it.get('function') or {}
        out.append(ToolCall(
            id=it.get('id'), name=fn.get('name', ''),
            arguments=fn.get('arguments') or '{}',
            provider_data=it.get('provider_data')))
    return out


def _flatten_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return ''.join(p.get('text', '') for p in content if isinstance(p, dict))
    return ''


def _to_input_content(role, content):
    text_type = 'output_text' if role == 'assistant' else 'input_text'
    if content is None:
        return []
    if isinstance(content, str):
        return [{'type': text_type, 'text': content}]
    parts = []
    for p in content:
        if isinstance(p, str):
            parts.append({'type': text_type, 'text': p})
        elif isinstance(p, dict):
            if p.get('type') == 'text':
                parts.append({'type': text_type, 'text': p.get('text', '')})
            elif p.get('type') == 'image_url':
                url = p.get('image_url')
                url = url.get('url') if isinstance(url, dict) else url
                parts.append({'type': 'input_image', 'image_url': url})
            else:
                parts.append(p)
    return parts


def _responses_tools(tools):
    out = []
    for t in tools or []:
        fn = t.get('function') or t
        out.append({
            'type': 'function', 'name': fn.get('name'),
            'description': fn.get('description', ''), 'strict': False,
            'parameters': fn.get('parameters') or {'type': 'object', 'properties': {}},
        })
    return out


# =============================================================================
# Codex image generation (gpt-image-2 via the /responses image_generation tool)
# =============================================================================
# Codex image generation. The ChatGPT/Codex OAuth
# token alone authorizes this (no billed OPENAI_API_KEY): a streaming /responses
# call where image generation is a tool; the PNG arrives base64 inside the SSE
# ``image_generation_call`` items.
CODEX_IMAGE_API_MODEL = 'gpt-image-2'
CODEX_IMAGE_INSTRUCTIONS = (
    "You are an assistant that must fulfill image generation requests by using "
    "the image_generation tool when provided.")
# aspect-ratio (our generic vocab + raw ratios) -> gpt-image-2 size
_CODEX_IMAGE_SIZES = {
    'landscape': '1536x1024', '16:9': '1536x1024', '3:2': '1536x1024',
    'square': '1024x1024', '1:1': '1024x1024',
    'portrait': '1024x1536', '9:16': '1024x1536', '2:3': '1024x1536',
}


def _codex_image_quality(model):
    """Map our virtual tier model ids -> gpt-image-2 ``quality`` (default medium)."""
    m = (model or '').lower()
    if m.endswith('-low'):
        return 'low'
    if m.endswith('-high'):
        return 'high'
    return 'medium'


def _codex_image_size(aspect):
    return _CODEX_IMAGE_SIZES.get((aspect or 'square').lower(), '1024x1024')


def _as_image_data_url(image):
    """Raw base64 -> ``data:`` URL; pass through existing URLs / data URLs.

    Accepts bytes/memoryview: Odoo ``fields.Image`` reads back as base64-ASCII
    *bytes*, not str (orm/fields_binary.py), so decode before string ops.
    """
    if isinstance(image, (bytes, bytearray, memoryview)):
        image = bytes(image).decode('ascii', 'ignore')
    s = image or ''
    if s.startswith(('http://', 'https://', 'data:')):
        return s
    return 'data:image/png;base64,%s' % s


def _extract_image_b64(value):
    """Recursively find the NEWEST base64 image in a decoded /responses SSE event.

    The final image is on an ``image_generation_call`` item's ``result`` field;
    intermediate frames arrive as ``partial_image_b64`` (we keep the latest).
    """
    found = None
    if isinstance(value, dict):
        if value.get('type') == 'image_generation_call':
            r = value.get('result')
            if isinstance(r, str) and r:
                found = r
        p = value.get('partial_image_b64')
        if isinstance(p, str) and p:
            found = p
        for child in value.values():
            nested = _extract_image_b64(child)
            if nested:
                found = nested
    elif isinstance(value, list):
        for child in value:
            nested = _extract_image_b64(child)
            if nested:
                found = nested
    return found


def generate_image_codex(base_url, headers, model, prompt, *, source_image=None,
                         proxy_url=None, extra=None, timeout=300.0):
    """Generate (or remix) an image on the ChatGPT/Codex OAuth via the /responses tool.

    When *source_image* is given (raw base64 / data URL / URL), it is attached as
    an ``input_image`` part so the model edits/remixes it (image-to-image).
    Returns ``{'images': [{'b64_json','url','mime_type'}]}`` (same shape as
    ``media_gen.generate_image`` so the model layer materializes it uniformly).
    """
    extra = extra or {}
    h = dict(headers)
    h.update(_codex_cloudflare_headers(h.get('Authorization', '')))
    h['Accept'] = 'text/event-stream'
    h.setdefault('Content-Type', 'application/json')
    _content = [{'type': 'input_text', 'text': prompt}]
    if source_image:
        _content.append({'type': 'input_image',
                         'image_url': _as_image_data_url(source_image)})
    body = {
        'model': 'gpt-5.5',           # host chat model that invokes the tool
        'store': False,
        'instructions': CODEX_IMAGE_INSTRUCTIONS,
        'input': [{'type': 'message', 'role': 'user', 'content': _content}],
        'tools': [{
            'type': 'image_generation', 'model': CODEX_IMAGE_API_MODEL,
            'size': _codex_image_size(extra.get('aspect_ratio')),
            'quality': _codex_image_quality(model),
            'output_format': 'png', 'background': 'opaque', 'partial_images': 1,
        }],
        # image generation is PLAN-GATED on the ChatGPT Codex backend: Team/Pro/
        # paid plans enable the image_generation tool (forcing it with this
        # allowed_tools tool_choice works); Free/Plus plans STRIP it (the request
        # echoes tools:[] and forcing it 400s "tool not found in 'tools'"). Both
        # verified live. We force it via allowed_tools and translate the free-plan
        # 400 into a clear message below.
        'tool_choice': {'type': 'allowed_tools', 'mode': 'required',
                        'tools': [{'type': 'image_generation'}]},
        'stream': True,
    }
    url = base_url.rstrip('/') + '/responses'
    b64 = None
    try:
        for event in http_client.post_sse(url, headers=h, json_body=body,
                                          timeout=timeout, proxy_url=proxy_url,
                                          impersonate='chrome'):
            b64 = _extract_image_b64(event) or b64
    except http_client.AiHttpError as exc:
        msg = str(exc).lower()
        if getattr(exc, 'status_code', None) == 400 and "not found in 'tools'" in msg:
            raise http_client.AiHttpError(
                400, "This ChatGPT account's plan doesn't support image generation "
                     "via Codex (it works on Team/Pro/paid plans, not Free/Plus). "
                     "Use a paid Codex credential, or xAI Grok for images.")
        raise
    if not b64:
        raise http_client.AiHttpError(
            0, "Codex returned no image (the image_generation tool isn't enabled on "
               "this account's plan — Team/Pro/paid required).")
    return {'images': [{'b64_json': b64, 'url': None, 'mime_type': 'image/png'}], 'raw': None}


@register_transport
class ResponsesTransport(Transport):
    api_mode = 'codex_responses'
    url_path = '/responses'

    def build_body(self, ctx: RequestContext) -> dict:
        instructions, items = _messages_to_input(ctx.messages)
        body = {'model': ctx.model, 'input': items, 'store': False,
                'instructions': instructions or DEFAULT_INSTRUCTIONS}
        if ctx.tools:
            body['tools'] = _responses_tools(ctx.tools)
            body['tool_choice'] = 'auto'
            body['parallel_tool_calls'] = True
        reasoning = ctx.extra.get('reasoning')
        if isinstance(reasoning, dict) and reasoning.get('enabled') is not False:
            body['reasoning'] = {'effort': (reasoning.get('effort') or 'medium'),
                                 'summary': 'auto'}
        max_tokens = ctx.max_tokens or ctx.provider.get('default_max_tokens') or None
        # The ChatGPT Codex backend rejects max_output_tokens (HTTP 400
        # "Unsupported parameter"); only standard /responses (xAI) accepts it.
        if max_tokens and not self._is_codex_backend(ctx):
            body['max_output_tokens'] = max_tokens
        if ctx.stream:
            body['stream'] = True
        body.update(ctx.extra.get('extra_body') or {})
        return body

    def parse_response(self, raw: dict, ctx: RequestContext) -> NormalizedResponse:
        text_parts, reasoning_parts, tool_calls = [], [], []
        for item in raw.get('output') or []:
            itype = item.get('type')
            if itype == 'message':
                for c in item.get('content') or []:
                    if c.get('type') in ('output_text', 'text'):
                        text_parts.append(c.get('text', ''))
            elif itype == 'reasoning':
                for s in item.get('summary') or []:
                    reasoning_parts.append(s.get('text', '') if isinstance(s, dict) else str(s))
            elif itype in ('function_call', 'tool_call'):
                tool_calls.append(ToolCall(
                    id=item.get('call_id') or item.get('id'),
                    name=item.get('name', ''),
                    arguments=item.get('arguments', '{}'),
                    provider_data={'call_id': item.get('call_id')} if item.get('call_id') else None))
        # convenience field some servers include
        if not text_parts and raw.get('output_text'):
            text_parts.append(raw['output_text'])
        usage = None
        u = raw.get('usage')
        if u:
            pt = u.get('input_tokens') or 0
            ct = u.get('output_tokens') or 0
            usage = Usage(prompt_tokens=pt, completion_tokens=ct, total_tokens=pt + ct)
        finish = 'tool_calls' if tool_calls else 'stop'
        return NormalizedResponse(
            content='\n'.join([t for t in text_parts if t]) or None,
            tool_calls=tool_calls or None, finish_reason=finish,
            reasoning='\n\n'.join([r for r in reasoning_parts if r]) or None, usage=usage)

    def _is_codex_backend(self, ctx: RequestContext) -> bool:
        """True for OpenAI's ChatGPT Codex backend (chatgpt.com/backend-api/
        codex), which has several quirks vs standard /responses (xAI Grok):
        it requires streaming, requires instructions, and rejects
        max_output_tokens / body-level extra_headers."""
        base = ctx.base_url or ctx.provider.get('base_url') or ''
        return ('chatgpt.com/backend-api/codex' in base
                or ctx.provider.get('code') == 'openai-codex')

    def _request_headers(self, ctx: RequestContext) -> dict:
        """Resolved auth headers + Codex-backend Cloudflare/account headers.

        Without ``originator: codex_cli_rs`` + the codex_cli_rs User-Agent +
        ``ChatGPT-Account-ID``, the Codex backend's Cloudflare 403s requests
        from server IPs — so a self-hosted Odoo can't reach Codex at all."""
        headers = dict(ctx.headers)
        if self._is_codex_backend(ctx):
            headers.update(_codex_cloudflare_headers(headers.get('Authorization', '')))
        return headers

    def _impersonate(self, ctx: RequestContext):
        """Use a browser TLS fingerprint for the ChatGPT Codex backend — its
        Cloudflare also fingerprints TLS, so the originator/UA headers alone
        may not clear a server IP."""
        return 'chrome' if self._is_codex_backend(ctx) else None

    def complete(self, ctx: RequestContext) -> NormalizedResponse:
        if not self._is_codex_backend(ctx):
            return super().complete(ctx)
        # Codex backend forbids non-streaming: consume the SSE stream and
        # aggregate it into a single NormalizedResponse — tool calls included.
        content_parts, final = [], {}
        for chunk in self.stream(ctx):
            if chunk.get('delta'):
                content_parts.append(chunk['delta'])
            if chunk.get('done'):
                final = chunk
        tool_calls = _tool_calls_from_dicts(final.get('tool_calls'))
        u = final.get('usage') or None
        usage = Usage(prompt_tokens=u.get('prompt_tokens', 0),
                      completion_tokens=u.get('completion_tokens', 0),
                      total_tokens=u.get('total_tokens', 0),
                      cached_tokens=u.get('cached_tokens', 0)) if u else None
        content = final.get('content') or ''.join(content_parts) or None
        return NormalizedResponse(
            content=content, tool_calls=tool_calls or None,
            finish_reason=final.get('finish_reason') or ('tool_calls' if tool_calls else 'stop'),
            reasoning=final.get('reasoning'), usage=usage)

    def stream(self, ctx: RequestContext):
        body = self.build_body(ctx)
        body['stream'] = True
        content_parts = []
        done_items = []   # output items finalized incrementally
        final = None
        for ev in http_client.post_sse(
                self.endpoint(ctx), headers=self._request_headers(ctx), json_body=body,
                timeout=max(ctx.timeout, 600.0), proxy_url=ctx.proxy_url,
                impersonate=self._impersonate(ctx)):
            etype = ev.get('type', '')
            if etype == 'response.output_text.delta':
                piece = ev.get('delta', '')
                if piece:
                    content_parts.append(piece)
                    yield {'delta': piece}
            elif etype == 'response.output_item.done':
                # The ChatGPT Codex backend delivers function calls ONLY here —
                # its 'response.completed' carries an empty output[] (verified
                # live). Collect the finalized tool-call items so they survive.
                item = ev.get('item')
                if isinstance(item, dict) and item.get('type') in ('function_call', 'tool_call'):
                    done_items.append(item)
            elif etype in ('response.completed', 'response.incomplete'):
                final = self.parse_response(ev.get('response') or {}, ctx)
        # Tool calls: prefer the terminal event (standard /responses, e.g. xAI),
        # else fall back to the incrementally-finalized items (the Codex backend,
        # or a stream cut off before the terminal event arrives).
        tool_calls = None
        if final is not None and final.tool_calls:
            tool_calls = [tc.to_dict() for tc in final.tool_calls]
        elif done_items:
            recovered = self.parse_response({'output': done_items}, ctx)
            if recovered.tool_calls:
                tool_calls = [tc.to_dict() for tc in recovered.tool_calls]
        content = (final.content if final and final.content else ''.join(content_parts)) or ''
        usage = final.usage.to_dict() if (final and final.usage) else None
        finish = ('tool_calls' if tool_calls
                  else (final.finish_reason if final else 'stop'))
        yield {
            'done': True, 'content': content, 'finish_reason': finish,
            'tool_calls': tool_calls, 'usage': usage,
            'reasoning': final.reasoning if final else None,
        }
