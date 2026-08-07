# -*- coding: utf-8 -*-
"""Per-provider request quirks (reasoning/thinking shaping, message prep).

The ``build_extra_body`` / ``build_api_kwargs_extras`` / ``prepare_messages``
hooks, keyed by provider ``code``. Kept as plain functions so the
``ai.provider`` seed stays pure data.

``reasoning`` is the caller's reasoning config: ``{'enabled': bool, 'effort':
'low'|'medium'|'high'|'xhigh'|'max'}`` or ``None``.

Each ``build_extras`` returns ``(extra_body_additions, top_level_kwargs,
extra_headers)``.
"""
from __future__ import annotations

import copy


def _flat(model):
    return (model or '').strip().rsplit('/', 1)[-1].lower()


# ── message preprocessing ───────────────────────────────────────────────
def prepare_messages(code, messages):
    """Provider-specific message preprocessing (default: pass-through)."""
    if code in ('qwen-oauth',):
        return _qwen_prepare(messages)
    return messages


def _qwen_prepare(messages):
    prepared = copy.deepcopy(messages or [])
    for msg in prepared:
        if not isinstance(msg, dict):
            continue
        content = msg.get('content')
        if isinstance(content, str):
            msg['content'] = [{'type': 'text', 'text': content}]
        elif isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, str):
                    parts.append({'type': 'text', 'text': part})
                elif isinstance(part, dict):
                    parts.append(part)
            if parts:
                msg['content'] = parts
    for msg in prepared:
        if isinstance(msg, dict) and msg.get('role') == 'system':
            content = msg.get('content')
            if isinstance(content, list) and content and isinstance(content[-1], dict):
                content[-1]['cache_control'] = {'type': 'ephemeral'}
            break
    return prepared


# ── reasoning / extra-body shaping ──────────────────────────────────────
def build_extras(code, model, reasoning, extra):
    """Return (extra_body_additions, top_level_kwargs, extra_headers)."""
    extra = extra or {}
    if code == 'deepseek':
        return _deepseek(model, reasoning)
    if code in ('kimi-coding', 'kimi-coding-cn'):
        return _kimi(reasoning)
    if code == 'opencode-go':
        return _opencode_go(model, reasoning)
    if code == 'openrouter':
        return _openrouter(model, reasoning, extra)
    if code in ('gemini', 'google-gemini-cli'):
        return _gemini(reasoning)
    if code == 'nous':
        return _nous(reasoning, extra)
    if code == 'copilot':
        return _copilot(reasoning)
    if code == 'custom':
        return _custom(reasoning, extra)
    if code == 'qwen-oauth':
        eb = {'vl_high_resolution_images': True}
        top = {}
        if extra.get('metadata'):
            top['metadata'] = extra['metadata']
        return eb, top, {}
    return {}, {}, {}


def _model_supports_thinking_deepseek(model):
    m = _flat(model)
    if not m:
        return False
    if m.startswith('deepseek-v') and not m.startswith('deepseek-v3'):
        return True
    return m == 'deepseek-reasoner'


def _deepseek(model, reasoning):
    extra_body, top = {}, {}
    if not _model_supports_thinking_deepseek(model):
        return extra_body, top, {}
    enabled = True
    if isinstance(reasoning, dict) and reasoning.get('enabled') is False:
        enabled = False
    extra_body['thinking'] = {'type': 'enabled' if enabled else 'disabled'}
    if not enabled:
        return extra_body, top, {}
    if isinstance(reasoning, dict):
        effort = (reasoning.get('effort') or '').strip().lower()
        if effort in {'xhigh', 'max'}:
            top['reasoning_effort'] = 'max'
        elif effort in {'low', 'medium', 'high'}:
            top['reasoning_effort'] = effort
    return extra_body, top, {}


def _kimi(reasoning):
    extra_body, top = {}, {}
    if not reasoning or not isinstance(reasoning, dict):
        extra_body['thinking'] = {'type': 'enabled'}
        return extra_body, top, {}
    if reasoning.get('enabled') is False:
        extra_body['thinking'] = {'type': 'disabled'}
        return extra_body, top, {}
    effort = (reasoning.get('effort') or '').strip().lower()
    if effort in {'low', 'medium', 'high'}:
        top['reasoning_effort'] = effort
    else:
        extra_body['thinking'] = {'type': 'enabled'}
    return extra_body, top, {}


def _opencode_go(model, reasoning):
    extra_body, top = {}, {}
    m = _flat(model)
    is_kimi = m.startswith('kimi-k2')
    is_ds = (m.startswith('deepseek-v') and not m.startswith('deepseek-v3')) or m == 'deepseek-reasoner'
    if not (is_kimi or is_ds):
        return extra_body, top, {}
    if not isinstance(reasoning, dict):
        return extra_body, top, {}
    if reasoning.get('enabled') is False:
        extra_body['thinking'] = {'type': 'disabled'}
        return extra_body, top, {}
    effort = (reasoning.get('effort') or '').strip().lower()
    if is_kimi:
        if effort in {'xhigh', 'max'}:
            top['reasoning_effort'] = 'high'
        elif effort in {'low', 'medium', 'high'}:
            top['reasoning_effort'] = effort
    else:
        if effort in {'xhigh', 'max'}:
            top['reasoning_effort'] = 'max'
        elif effort in {'low', 'medium', 'high'}:
            top['reasoning_effort'] = effort
    if 'reasoning_effort' not in top:
        extra_body['thinking'] = {'type': 'enabled'}
    return extra_body, top, {}


_ANTHROPIC_REASONING_OPTIONAL = (
    'claude-3', 'claude-opus-4-0', 'claude-opus-4.0', 'claude-opus-4-1',
    'claude-opus-4.1', 'claude-sonnet-4-0', 'claude-sonnet-4.0',
    'claude-opus-4-2025', 'claude-sonnet-4-2025', 'claude-opus-4-5',
    'claude-opus-4.5', 'claude-sonnet-4-5', 'claude-sonnet-4.5',
    'claude-haiku-4-5', 'claude-haiku-4.5',
)


def _anthropic_reasoning_mandatory(model):
    m = (model or '').lower()
    if not m.startswith(('anthropic/', 'claude')) and 'claude' not in m:
        return False
    return not any(s in m for s in _ANTHROPIC_REASONING_OPTIONAL)


def _openrouter(model, reasoning, extra):
    extra_body, top, headers = {}, {}, {}
    session_id = extra.get('session_id')
    if session_id:
        extra_body['session_id'] = session_id
    if extra.get('provider_preferences'):
        extra_body['provider'] = extra['provider_preferences']
    if reasoning is not None:
        if _anthropic_reasoning_mandatory(model):
            cfg = reasoning or {}
            effort = cfg.get('effort')
            if cfg.get('enabled', True) is not False and effort and effort != 'none':
                top['verbosity'] = effort
        elif isinstance(reasoning, dict):
            extra_body['reasoning'] = dict(reasoning)
        else:
            extra_body['reasoning'] = {'enabled': True, 'effort': 'medium'}
    if session_id and model and model.startswith(('x-ai/grok-', 'xai/grok-')):
        headers['x-grok-conv-id'] = session_id
    return extra_body, top, headers


def _gemini(reasoning):
    if not isinstance(reasoning, dict) or reasoning.get('enabled') is False:
        return {}, {}, {}
    effort = (reasoning.get('effort') or 'medium').strip().lower()
    budget_map = {'low': 1024, 'medium': 8192, 'high': 24576, 'xhigh': 32768, 'max': 32768}
    return {'thinking_config': {'thinking_budget': budget_map.get(effort, 8192)}}, {}, {}


def _nous(reasoning, extra):
    extra_body = {'tags': extra.get('tags') or ['odoo-ai-connector']}
    if reasoning is not None:
        if isinstance(reasoning, dict) and reasoning.get('enabled') is False:
            pass
        elif isinstance(reasoning, dict):
            extra_body['reasoning'] = dict(reasoning)
        else:
            extra_body['reasoning'] = {'enabled': True, 'effort': 'medium'}
    return extra_body, {}, {}


def _copilot(reasoning):
    extra_body = {}
    if isinstance(reasoning, dict) and reasoning.get('enabled') is not False:
        effort = reasoning.get('effort', 'medium')
        if effort == 'xhigh':
            effort = 'high'
        if effort in {'low', 'medium', 'high'}:
            extra_body['reasoning'] = {'effort': effort}
    return extra_body, {}, {}


def _custom(reasoning, extra):
    extra_body = {}
    num_ctx = extra.get('ollama_num_ctx')
    if num_ctx:
        extra_body['options'] = {'num_ctx': num_ctx}
    if isinstance(reasoning, dict):
        effort = (reasoning.get('effort') or '').strip().lower()
        if effort == 'none' or reasoning.get('enabled') is False:
            extra_body['think'] = False
    return extra_body, {}, {}
