# -*- coding: utf-8 -*-
"""Google Cloud Code Assist transport (api_mode='gemini_cloudcode').

The ``google-gemini-cli`` provider authenticates via OAuth (PKCE) and then
talks to Google's **internal Code Assist API** at
``cloudcode-pa.googleapis.com`` using a Gemini-native request/response shape —
NOT the OpenAI chat-completions wire format the OpenAI transport speaks. The
provider's ``base_url`` (``cloudcode-pa://google``) is just a marker that
selects this transport.

This module:
  * translates OpenAI ``messages[]`` / ``tools[]`` / ``tool_choice``  →  Gemini
    ``contents[]`` / ``functionDeclarations`` / ``toolConfig`` / ``systemInstruction``,
  * wraps the request in the Code Assist envelope ``{project, model,
    user_prompt_id, request}``,
  * POSTs to ``v1internal:{generateContent, streamGenerateContent}`` through the
    SSRF-guarded :mod:`http_client`,
  * translates the Gemini response back into our :class:`NormalizedResponse`.

The GCP *project* needed for the envelope is resolved/persisted in the model
layer (see ``ai.credential._ensure_gemini_project``) and handed in via
``ctx.extra['gemini_project_id']``. Project *discovery* (loadCodeAssist /
onboardUser) lives here so all Code Assist HTTP stays in one place.

Attribution: the (publicly undocumented) Code Assist envelope shape is derived
from jenslys/opencode-gemini-auth (MIT) and the public Gemini API docs.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from . import http_client
from .http_client import AiHttpError
from .transport_base import Transport, RequestContext, register_transport
from .types import NormalizedResponse, ToolCall, Usage

_logger = logging.getLogger(__name__)

CODE_ASSIST_ENDPOINT = 'https://cloudcode-pa.googleapis.com'
# Tried in order during project discovery when prod errors.
_FALLBACK_ENDPOINTS = [
    'https://daily-cloudcode-pa.sandbox.googleapis.com',
    'https://autopush-cloudcode-pa.sandbox.googleapis.com',
]
MARKER_BASE_URL = 'cloudcode-pa://google'

_FREE_TIER_ID = 'free-tier'
_LEGACY_TIER_ID = 'legacy-tier'
_STANDARD_TIER_ID = 'standard-tier'

# Match Google's gemini-cli fingerprint — these internal endpoints may reject
# unrecognized User-Agents / API-client tags.
_GEMINI_CLI_USER_AGENT = 'google-api-nodejs-client/9.15.1 (gzip)'
_X_GOOG_API_CLIENT = 'gl-node/24.0.0'

# Onboarding can be a long-running operation; poll briefly so a brand-new
# free-tier account gets provisioned without hanging the request for a minute.
_ONBOARD_POLL_ATTEMPTS = 6
_ONBOARD_POLL_INTERVAL = 3.0


# =============================================================================
# Tool-schema sanitizer (Gemini Schema is a JSON-Schema subset)
# =============================================================================

_GEMINI_SCHEMA_ALLOWED_KEYS = {
    'type', 'format', 'title', 'description', 'nullable', 'enum',
    'maxItems', 'minItems', 'properties', 'required', 'minProperties',
    'maxProperties', 'minLength', 'maxLength', 'pattern', 'example',
    'anyOf', 'propertyOrdering', 'default', 'items', 'minimum', 'maximum',
}


def sanitize_gemini_schema(schema: Any) -> dict:
    """Gemini-compatible copy of a tool-parameter schema (drops unknown keys)."""
    if not isinstance(schema, dict):
        return {}
    cleaned: dict = {}
    for key, value in schema.items():
        if key not in _GEMINI_SCHEMA_ALLOWED_KEYS:
            continue
        if key == 'properties':
            if not isinstance(value, dict):
                continue
            cleaned[key] = {
                name: sanitize_gemini_schema(sub)
                for name, sub in value.items() if isinstance(name, str)
            }
            continue
        if key == 'items':
            cleaned[key] = sanitize_gemini_schema(value)
            continue
        if key == 'anyOf':
            if not isinstance(value, list):
                continue
            cleaned[key] = [sanitize_gemini_schema(i) for i in value if isinstance(i, dict)]
            continue
        cleaned[key] = value
    # Gemini requires enum entries to be strings even for numeric/bool types.
    enum_val = cleaned.get('enum')
    if isinstance(enum_val, list) and cleaned.get('type') in {'integer', 'number', 'boolean'}:
        if any(not isinstance(i, str) for i in enum_val):
            cleaned.pop('enum', None)
    return cleaned


def sanitize_gemini_tool_parameters(parameters: Any) -> dict:
    cleaned = sanitize_gemini_schema(parameters)
    return cleaned or {'type': 'object', 'properties': {}}


# =============================================================================
# Request translation: OpenAI -> Gemini
# =============================================================================

_ROLE_MAP = {'user': 'user', 'assistant': 'model', 'system': 'user',
             'tool': 'user', 'function': 'user'}


def _coerce_text(content: Any) -> str:
    """OpenAI content may be str or a list of parts; reduce to plain text."""
    if content is None:
        return ''
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces = []
        for p in content:
            if isinstance(p, str):
                pieces.append(p)
            elif isinstance(p, dict):
                if p.get('type') == 'text' and isinstance(p.get('text'), str):
                    pieces.append(p['text'])
                elif p.get('type') in {'image_url', 'input_audio'}:
                    _logger.debug("gemini_cloudcode: dropping multimodal part %s", p.get('type'))
        return '\n'.join(pieces)
    return str(content)


def _tool_call_to_gemini(tc: dict) -> dict:
    fn = tc.get('function') or {}
    args_raw = fn.get('arguments', '')
    try:
        args = json.loads(args_raw) if isinstance(args_raw, str) and args_raw else {}
    except json.JSONDecodeError:
        args = {'_raw': args_raw}
    if not isinstance(args, dict):
        args = {'_value': args}
    return {
        'functionCall': {'name': fn.get('name') or '', 'args': args},
        # Sentinel signature — Code Assist rejects function calls that
        # originated outside its own chain without it.
        'thoughtSignature': 'skip_thought_signature_validator',
    }


def _tool_result_to_gemini(message: dict) -> dict:
    name = str(message.get('name') or message.get('tool_call_id') or 'tool')
    content = _coerce_text(message.get('content'))
    try:
        parsed = json.loads(content) if content.strip().startswith(('{', '[')) else None
    except json.JSONDecodeError:
        parsed = None
    response = parsed if isinstance(parsed, dict) else {'output': content}
    return {'functionResponse': {'name': name, 'response': response}}


def _build_contents(messages: list) -> tuple[list, dict | None]:
    """OpenAI messages[] -> (Gemini contents[], systemInstruction|None)."""
    system_parts: list[str] = []
    contents: list[dict] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get('role') or 'user')
        if role == 'system':
            system_parts.append(_coerce_text(msg.get('content')))
            continue
        if role in ('tool', 'function'):
            contents.append({'role': 'user', 'parts': [_tool_result_to_gemini(msg)]})
            continue
        parts: list[dict] = []
        text = _coerce_text(msg.get('content'))
        if text:
            parts.append({'text': text})
        for tc in msg.get('tool_calls') or []:
            if isinstance(tc, dict):
                parts.append(_tool_call_to_gemini(tc))
        if not parts:
            continue  # Gemini rejects empty parts
        contents.append({'role': _ROLE_MAP.get(role, 'user'), 'parts': parts})
    system_instruction = None
    joined = '\n'.join(p for p in system_parts if p).strip()
    if joined:
        system_instruction = {'role': 'system', 'parts': [{'text': joined}]}
    return contents, system_instruction


def _tools_to_gemini(tools: Any) -> list:
    if not isinstance(tools, list) or not tools:
        return []
    decls = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        fn = t.get('function') or {}
        if not isinstance(fn, dict) or not fn.get('name'):
            continue
        decl = {'name': str(fn['name'])}
        if fn.get('description'):
            decl['description'] = str(fn['description'])
        if isinstance(fn.get('parameters'), dict):
            decl['parameters'] = sanitize_gemini_tool_parameters(fn['parameters'])
        decls.append(decl)
    return [{'functionDeclarations': decls}] if decls else []


def _tool_choice_to_gemini(tool_choice: Any) -> dict | None:
    if tool_choice is None:
        return None
    if isinstance(tool_choice, str):
        return {
            'auto': {'functionCallingConfig': {'mode': 'AUTO'}},
            'required': {'functionCallingConfig': {'mode': 'ANY'}},
            'none': {'functionCallingConfig': {'mode': 'NONE'}},
        }.get(tool_choice)
    if isinstance(tool_choice, dict):
        name = (tool_choice.get('function') or {}).get('name')
        if name:
            return {'functionCallingConfig': {'mode': 'ANY',
                                              'allowedFunctionNames': [str(name)]}}
    return None


def _normalize_thinking_config(config: Any) -> dict | None:
    if not isinstance(config, dict) or not config:
        return None
    budget = config.get('thinkingBudget', config.get('thinking_budget'))
    level = config.get('thinkingLevel', config.get('thinking_level'))
    include = config.get('includeThoughts', config.get('include_thoughts'))
    out: dict = {}
    if isinstance(budget, (int, float)):
        out['thinkingBudget'] = int(budget)
    if isinstance(level, str) and level.strip():
        out['thinkingLevel'] = level.strip().lower()
    if isinstance(include, bool):
        out['includeThoughts'] = include
    return out or None


def build_gemini_request(ctx: RequestContext) -> dict:
    """Inner Gemini request body (goes inside the Code Assist ``request`` wrapper)."""
    contents, system_instruction = _build_contents(ctx.messages)
    body: dict = {'contents': contents}
    if system_instruction is not None:
        body['systemInstruction'] = system_instruction

    gemini_tools = _tools_to_gemini(ctx.tools)
    if gemini_tools:
        body['tools'] = gemini_tools
    tool_cfg = _tool_choice_to_gemini(ctx.tool_choice)
    if tool_cfg is not None:
        body['toolConfig'] = tool_cfg

    gen: dict = {}
    if isinstance(ctx.temperature, (int, float)):
        gen['temperature'] = float(ctx.temperature)
    max_tokens = ctx.max_tokens or ctx.provider.get('default_max_tokens')
    if isinstance(max_tokens, int) and max_tokens > 0:
        gen['maxOutputTokens'] = max_tokens
    extra = ctx.extra or {}
    top_p = extra.get('top_p')
    if isinstance(top_p, (int, float)):
        gen['topP'] = float(top_p)
    stop = extra.get('stop')
    if isinstance(stop, str) and stop:
        gen['stopSequences'] = [stop]
    elif isinstance(stop, list) and stop:
        gen['stopSequences'] = [str(s) for s in stop if s]
    eb = extra.get('extra_body') if isinstance(extra.get('extra_body'), dict) else {}
    thinking = _normalize_thinking_config(
        extra.get('thinking_config') or extra.get('thinkingConfig')
        or eb.get('thinking_config') or eb.get('thinkingConfig'))
    if thinking:
        gen['thinkingConfig'] = thinking
    if gen:
        body['generationConfig'] = gen
    return body


def wrap_request(project_id: str, model: str, inner: dict) -> dict:
    return {
        'project': project_id or '',
        'model': model,
        'user_prompt_id': str(uuid.uuid4()),
        'request': inner,
    }


# =============================================================================
# Response translation: Gemini -> NormalizedResponse
# =============================================================================

_FINISH_MAP = {'STOP': 'stop', 'MAX_TOKENS': 'length', 'SAFETY': 'content_filter',
               'RECITATION': 'content_filter', 'OTHER': 'stop'}


def _map_finish(reason: str) -> str:
    return _FINISH_MAP.get((reason or '').upper(), 'stop')


def _candidate_parts(payload: dict) -> tuple[dict, list]:
    """Unwrap the Code Assist ``response`` envelope; return (inner, parts)."""
    inner = payload.get('response') if isinstance(payload.get('response'), dict) else payload
    candidates = inner.get('candidates') or []
    if not isinstance(candidates, list) or not candidates:
        return inner, []
    cand = candidates[0] if isinstance(candidates[0], dict) else {}
    content = cand.get('content') if isinstance(cand.get('content'), dict) else {}
    return inner, (content.get('parts') or [])


def parse_gemini_response(payload: dict, ctx: RequestContext) -> NormalizedResponse:
    inner = payload.get('response') if isinstance(payload.get('response'), dict) else payload
    candidates = inner.get('candidates') or []
    cand = candidates[0] if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict) else {}
    content_obj = cand.get('content') if isinstance(cand.get('content'), dict) else {}
    parts = content_obj.get('parts') or []

    text_pieces: list[str] = []
    reasoning_pieces: list[str] = []
    tool_calls: list[ToolCall] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        if part.get('thought') is True:
            if isinstance(part.get('text'), str):
                reasoning_pieces.append(part['text'])
            continue
        if isinstance(part.get('text'), str):
            text_pieces.append(part['text'])
            continue
        fc = part.get('functionCall')
        if isinstance(fc, dict) and fc.get('name'):
            try:
                args = json.dumps(fc.get('args') or {}, ensure_ascii=False)
            except (TypeError, ValueError):
                args = '{}'
            tool_calls.append(ToolCall(
                id='call_%s' % uuid.uuid4().hex[:12], name=str(fc['name']), arguments=args))

    usage_meta = inner.get('usageMetadata') or {}
    usage = Usage(
        prompt_tokens=int(usage_meta.get('promptTokenCount') or 0),
        completion_tokens=int(usage_meta.get('candidatesTokenCount') or 0),
        total_tokens=int(usage_meta.get('totalTokenCount') or 0),
        cached_tokens=int(usage_meta.get('cachedContentTokenCount') or 0),
    )
    finish = 'tool_calls' if tool_calls else _map_finish(str(cand.get('finishReason') or ''))
    return NormalizedResponse(
        content=''.join(text_pieces) or None,
        tool_calls=tool_calls or None,
        finish_reason=finish,
        reasoning=''.join(reasoning_pieces) or None,
        usage=usage,
    )


# =============================================================================
# HTTP helpers
# =============================================================================

def _inference_headers(ctx: RequestContext) -> dict:
    """Build Code Assist headers, carrying the OAuth bearer from resolved auth."""
    token = ''
    authz = (ctx.headers or {}).get('Authorization') or ''
    if authz.startswith('Bearer '):
        token = authz[len('Bearer '):]
    if not token:
        raise AiHttpError(0, "Gemini CLI: no OAuth access token resolved.")
    return {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': 'Bearer %s' % token,
        'User-Agent': _GEMINI_CLI_USER_AGENT,
        'X-Goog-Api-Client': _X_GOOG_API_CLIENT,
        'x-activity-request-id': str(uuid.uuid4()),
    }


def _control_headers(access_token: str) -> dict:
    return {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': 'Bearer %s' % access_token,
        'User-Agent': _GEMINI_CLI_USER_AGENT,
        'X-Goog-Api-Client': _X_GOOG_API_CLIENT,
        'x-activity-request-id': str(uuid.uuid4()),
    }


def _client_metadata() -> dict:
    return {'ideType': 'IDE_UNSPECIFIED', 'platform': 'PLATFORM_UNSPECIFIED',
            'pluginType': 'GEMINI'}


def _is_vpc_sc_violation(body: Any) -> bool:
    if isinstance(body, dict):
        err = body.get('error') if isinstance(body.get('error'), dict) else {}
        for item in (err.get('details') or []):
            if isinstance(item, dict) and item.get('reason') == 'SECURITY_POLICY_VIOLATED':
                return True
        return 'SECURITY_POLICY_VIOLATED' in str(err.get('message') or '')
    return 'SECURITY_POLICY_VIOLATED' in str(body or '')


# =============================================================================
# Project-context resolution (loadCodeAssist / onboardUser)
# =============================================================================

def _parse_load_response(resp: dict) -> tuple[str, str, list]:
    """Return (tier_id, cloudaicompanion_project, allowed_tier_ids)."""
    current = resp.get('currentTier') or {}
    tier_id = str(current.get('id') or '') if isinstance(current, dict) else ''
    project = str(resp.get('cloudaicompanionProject') or '')
    allowed = []
    for t in (resp.get('allowedTiers') or []):
        if isinstance(t, dict) and t.get('id'):
            allowed.append(str(t['id']))
    return tier_id, project, allowed


def load_code_assist(access_token: str, *, project_id: str = '', timeout: float = 30.0) -> dict:
    """POST /v1internal:loadCodeAssist with prod -> sandbox fallback.

    Returns ``{'tier_id', 'project'}``. On a VPC-SC violation, returns
    standard-tier so the chain can continue.
    """
    body: dict = {'metadata': {'duetProject': project_id, **_client_metadata()}}
    if project_id:
        body['cloudaicompanionProject'] = project_id
    headers = _control_headers(access_token)
    last_exc = None
    for endpoint in [CODE_ASSIST_ENDPOINT] + _FALLBACK_ENDPOINTS:
        url = '%s/v1internal:loadCodeAssist' % endpoint
        try:
            resp = http_client.post_json(url, headers=headers, json_body=body,
                                         timeout=timeout, max_retries=1)
            tier_id, project, _allowed = _parse_load_response(resp)
            return {'tier_id': tier_id, 'project': project}
        except AiHttpError as exc:
            if _is_vpc_sc_violation(exc.body):
                _logger.info("gemini_cloudcode: VPC-SC violation, defaulting to standard-tier")
                return {'tier_id': _STANDARD_TIER_ID, 'project': project_id}
            last_exc = exc
            _logger.warning("loadCodeAssist failed on %s: %s", endpoint, exc)
    if last_exc:
        raise last_exc
    return {'tier_id': '', 'project': ''}


def onboard_user(access_token: str, *, tier_id: str, project_id: str = '',
                 timeout: float = 30.0) -> dict:
    """POST /v1internal:onboardUser; poll briefly if it's a long-running op."""
    import time
    body: dict = {'tierId': tier_id, 'metadata': _client_metadata()}
    if project_id:
        body['cloudaicompanionProject'] = project_id
    headers = _control_headers(access_token)
    url = '%s/v1internal:onboardUser' % CODE_ASSIST_ENDPOINT
    resp = http_client.post_json(url, headers=headers, json_body=body,
                                 timeout=timeout, max_retries=1)
    if resp.get('done'):
        return resp
    op_name = resp.get('name') or ''
    if not op_name:
        return resp
    poll_url = '%s/v1internal/%s' % (CODE_ASSIST_ENDPOINT, op_name)
    for _attempt in range(_ONBOARD_POLL_ATTEMPTS):
        time.sleep(_ONBOARD_POLL_INTERVAL)
        try:
            poll = http_client.post_json(poll_url, headers=headers, json_body={},
                                         timeout=timeout, max_retries=0)
        except AiHttpError as exc:
            _logger.warning("onboardUser poll failed: %s", exc)
            continue
        if poll.get('done'):
            return poll
    return resp


def resolve_project_id(access_token: str, *, configured_project_id: str = '',
                       timeout: float = 30.0) -> str:
    """Figure out the GCP project for the Code Assist envelope.

    Priority: an explicitly configured project wins. Otherwise discover via
    loadCodeAssist; if the account isn't onboarded yet, provision it on the
    free tier and use the assigned managed project.
    """
    if configured_project_id:
        return configured_project_id
    info = load_code_assist(access_token, timeout=timeout)
    project = info.get('project') or ''
    tier = info.get('tier_id') or ''
    if not tier:
        onboard = onboard_user(access_token, tier_id=_FREE_TIER_ID, timeout=timeout)
        response_body = onboard.get('response') if isinstance(onboard.get('response'), dict) else {}
        project = project or str(response_body.get('cloudaicompanionProject') or '')
    return project


# =============================================================================
# Transport
# =============================================================================

@register_transport
class GeminiCloudCodeTransport(Transport):
    api_mode = 'gemini_cloudcode'
    url_path = ''  # endpoints are method-style (:generateContent), built below

    def build_body(self, ctx: RequestContext) -> dict:
        project_id = (ctx.extra or {}).get('gemini_project_id') or ''
        return wrap_request(project_id, ctx.model, build_gemini_request(ctx))

    def complete(self, ctx: RequestContext) -> NormalizedResponse:
        url = '%s/v1internal:generateContent' % CODE_ASSIST_ENDPOINT
        payload = http_client.post_json(
            url, headers=_inference_headers(ctx), json_body=self.build_body(ctx),
            timeout=ctx.timeout, proxy_url=ctx.proxy_url)
        return self.parse_response(payload, ctx)

    def parse_response(self, raw: dict, ctx: RequestContext) -> NormalizedResponse:
        return parse_gemini_response(raw, ctx)

    def stream(self, ctx: RequestContext):
        url = '%s/v1internal:streamGenerateContent?alt=sse' % CODE_ASSIST_ENDPOINT
        headers = _inference_headers(ctx)
        headers['Accept'] = 'text/event-stream'
        content_parts: list[str] = []
        tool_acc: dict[int, dict] = {}
        finish_reason = 'stop'
        usage = None
        tool_idx = 0
        for event in http_client.post_sse(
                url, headers=headers, json_body=self.build_body(ctx),
                timeout=max(ctx.timeout, 600.0), proxy_url=ctx.proxy_url):
            inner = event.get('response') if isinstance(event.get('response'), dict) else event
            cands = inner.get('candidates') or []
            if not cands or not isinstance(cands[0], dict):
                # Usage may arrive on a candidate-less terminal event.
                um = inner.get('usageMetadata')
                if um:
                    usage = {
                        'prompt_tokens': int(um.get('promptTokenCount') or 0),
                        'completion_tokens': int(um.get('candidatesTokenCount') or 0),
                        'total_tokens': int(um.get('totalTokenCount') or 0),
                    }
                continue
            cand = cands[0]
            content = cand.get('content') if isinstance(cand.get('content'), dict) else {}
            for part in (content.get('parts') or []):
                if not isinstance(part, dict):
                    continue
                if part.get('thought') is True:
                    continue  # reasoning deltas are not surfaced mid-stream
                txt = part.get('text')
                if isinstance(txt, str) and txt:
                    content_parts.append(txt)
                    yield {'delta': txt}
                fc = part.get('functionCall')
                if isinstance(fc, dict) and fc.get('name'):
                    try:
                        args = json.dumps(fc.get('args') or {}, ensure_ascii=False)
                    except (TypeError, ValueError):
                        args = '{}'
                    tool_acc[tool_idx] = {
                        'id': 'call_%s' % uuid.uuid4().hex[:12],
                        'name': str(fc['name']), 'arguments': args}
                    tool_idx += 1
            um = inner.get('usageMetadata')
            if um:
                usage = {
                    'prompt_tokens': int(um.get('promptTokenCount') or 0),
                    'completion_tokens': int(um.get('candidatesTokenCount') or 0),
                    'total_tokens': int(um.get('totalTokenCount') or 0),
                }
            if cand.get('finishReason'):
                finish_reason = _map_finish(str(cand['finishReason']))
        tool_calls = None
        if tool_acc:
            finish_reason = 'tool_calls'
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
