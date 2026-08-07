# -*- coding: utf-8 -*-
"""Routing + Odoo↔connector translation for the native-AI bridge.

Odoo's ``LLMApiService._request_llm`` is called by the tool loop as
``_request_llm(llm_model, system_prompts, user_prompts, files=, inputs=,
schema=, tools=, temperature=, web_grounding=)`` and must return
``(response: list[str], to_call: list[(name, call_id, args)], next_inputs:
list[dict])``. We build OpenAI chat ``messages`` from the Odoo inputs, call
``ai.connector.chat()``, and map its NormalizedResponse back to that tuple —
keeping OpenAI ``function_call`` / ``function_call_output`` item shapes so the
loop's tool round-trip (which branches on ``provider == 'openai'``) is closed.
"""
import json
import logging

_logger = logging.getLogger(__name__)


def route(env, llm_model):
    """(provider_code, model_id, credential_id|None) to route through the
    connector, else None.

    Active when the admin enabled the bridge. Uses the bridge's own Provider /
    Account / Model settings, falling back to the connector's gateway Default
    Provider/Model when those are blank. ``oconn:<provider>/<model>`` agent
    models force routing (no credential → provider default).
    """
    if isinstance(llm_model, str) and llm_model.startswith('oconn:'):
        body = llm_model[len('oconn:'):]
        if '/' in body:
            prov, model = body.split('/', 1)
            if prov and model:
                return prov, model, None
    icp = env['ir.config_parameter'].sudo()
    if icp.get_param('ai_connector_bridge.enabled') not in ('True', 'true', '1'):
        return None
    prov_id = (icp.get_param('ai_connector_bridge.provider_id')
               or icp.get_param('open_ai_connector.default_provider_id'))
    model = (icp.get_param('ai_connector_bridge.model')
             or icp.get_param('open_ai_connector.default_model'))
    if not (prov_id and model):
        return None
    try:
        prov = env['ai.provider'].sudo().browse(int(prov_id))
    except (ValueError, TypeError):
        return None
    if not prov.exists() or not prov.code:
        return None
    cred_raw = icp.get_param('ai_connector_bridge.credential_id')
    try:
        credential_id = int(cred_raw) if cred_raw else None
    except (ValueError, TypeError):
        credential_id = None
    return prov.code, model, credential_id


# ── message translation ──────────────────────────────────────────────────
def _file_to_part(f):
    mt = (f.get('mimetype') or '').lower()
    val = f.get('value') or ''
    if mt == 'text/plain':
        return {'type': 'text', 'text': val}
    if mt.startswith('image/'):
        return {'type': 'image_url', 'image_url': {'url': 'data:%s;base64,%s' % (mt, val)}}
    # The generic chat path can't carry other binaries (e.g. pdf); note it.
    return {'type': 'text', 'text': '[attachment omitted: %s]' % (mt or 'unknown')}


def _content_to_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for p in content:
            if isinstance(p, str):
                out.append(p)
            elif isinstance(p, dict) and p.get('type') in ('input_text', 'output_text', 'text'):
                out.append(p.get('text', ''))
        return '\n'.join(out)
    return str(content or '')


def _inputs_to_messages(inputs):
    """Odoo /responses-shaped accumulator items -> OpenAI chat messages."""
    msgs = []
    for it in inputs or ():
        if not isinstance(it, dict):
            continue
        itype = it.get('type')
        if itype == 'function_call':
            msgs.append({
                'role': 'assistant', 'content': None,
                'tool_calls': [{
                    'id': it.get('call_id') or it.get('name'),
                    'type': 'function',
                    'function': {'name': it.get('name'),
                                 'arguments': it.get('arguments') or '{}'},
                }],
            })
        elif itype == 'function_call_output':
            msgs.append({'role': 'tool', 'tool_call_id': it.get('call_id'),
                         'content': str(it.get('output') or '')})
        elif it.get('role'):
            msgs.append({'role': it['role'], 'content': _content_to_text(it.get('content'))})
    return msgs


def build_messages(system_prompts, user_prompts, files, inputs):
    messages = []
    sys_text = '\n'.join(p for p in (system_prompts or []) if p)
    if sys_text:
        messages.append({'role': 'system', 'content': sys_text})
    parts = [{'type': 'text', 'text': p} for p in (user_prompts or []) if p]
    parts += [_file_to_part(f) for f in (files or [])]
    if parts:
        if len(parts) == 1 and parts[0].get('type') == 'text':
            messages.append({'role': 'user', 'content': parts[0]['text']})
        else:
            messages.append({'role': 'user', 'content': parts})
    messages.extend(_inputs_to_messages(inputs))
    return messages


def tools_to_openai(tools):
    """Odoo tools dict {name: (desc, allow_end, callable, schema)} -> OpenAI tools."""
    out = []
    for name, spec in (tools or {}).items():
        desc = spec[0] if len(spec) > 0 else ''
        pschema = spec[3] if len(spec) > 3 else {'type': 'object', 'properties': {}}
        out.append({'type': 'function',
                    'function': {'name': name, 'description': desc, 'parameters': pschema}})
    return out


# ── the connector call ─────────────────────────────────────────────────────
def request_via_connector(service, provider, model, llm_model, system_prompts,
                          user_prompts, tools=None, files=None, schema=None,
                          temperature=0.2, inputs=(), web_grounding=False,
                          credential_id=None):
    """Run one LLM turn through ai.connector.chat(); return Odoo's 3-tuple."""
    env = service.env
    messages = build_messages(system_prompts, user_prompts, files, inputs)
    openai_tools = tools_to_openai(tools)
    extra = None
    if schema:
        # Best effort — honored by OpenAI-compatible providers; others ignore it.
        extra = {'extra_body': {'response_format': {
            'type': 'json_schema',
            'json_schema': {'name': 'json_schema', 'schema': schema, 'strict': True}}}}
    # sudo: native-AI callers may not be in group_ai_user; the admin opted in by
    # enabling the bridge, and the connector logs every call to ai.completion.log.
    result = env['ai.connector'].sudo().chat(
        provider=provider, model=model, messages=messages,
        tools=openai_tools or None,
        tool_choice='auto' if openai_tools else None,
        temperature=temperature, extra=extra, credential=credential_id, stream=False)
    next_inputs = list(inputs or ())
    tool_calls = result.get('tool_calls') or []
    if tool_calls:
        to_call = []
        for c in tool_calls:
            fn = c.get('function') or {}
            name = fn.get('name')
            call_id = c.get('id') or name
            raw_args = fn.get('arguments') or '{}'
            try:
                args = json.loads(raw_args)
            except (ValueError, TypeError):
                args = {}
            to_call.append((name, call_id, args))
            next_inputs.append({'type': 'function_call', 'name': name,
                                'arguments': raw_args, 'call_id': call_id})
        return [], to_call, next_inputs
    content = result.get('content')
    return ([content] if content else []), [], next_inputs
