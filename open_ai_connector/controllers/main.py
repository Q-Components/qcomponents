# -*- coding: utf-8 -*-
"""OpenAI-compatible HTTP gateway.

Exposes ``/ai/v1/chat/completions`` and ``/ai/v1/models`` so external apps can
use this Odoo instance as a unified AI gateway. Authentication is via an Odoo
user's API key (Authorization: Bearer <odoo-api-key>); that user must be in the
AI User group.
"""
import json
import logging
import time
import uuid

from odoo import http
from odoo.http import request
from werkzeug.wrappers import Response

_logger = logging.getLogger(__name__)


class AiGatewayController(http.Controller):

    # ── helpers ────────────────────────────────────────────────────────
    def _gateway_enabled(self):
        return request.env['ir.config_parameter'].sudo().get_param(
            'open_ai_connector.gateway_enabled', 'True') in ('True', 'true', '1')

    def _json_error(self, message, status=400, etype='invalid_request_error'):
        body = json.dumps({'error': {'message': message, 'type': etype}})
        return Response(body, status=status, content_type='application/json')

    def _require_ai_user(self):
        """Fail closed unless the bearer user is in the AI User group.

        auth='bearer' only proves the API key is valid for *some* user — it does
        no group check. Without this, any internal/portal user with an API key
        could reach the gateway. Returns an error Response, or None when allowed.
        """
        if not request.env.user.has_group('open_ai_connector.group_ai_user'):
            return self._json_error("You are not allowed to use the AI gateway.",
                                    status=403, etype='permission_error')
        return None

    def _int_param(self, key, default):
        try:
            return int(request.env['ir.config_parameter'].sudo().get_param(key, default))
        except (ValueError, TypeError):
            return int(default)

    def _rate_limited(self):
        """Best-effort per-user throttle (counts this user's recent log rows).

        DB-backed so it holds across workers. 0 disables it. Returns an error
        Response when the caller is over the limit, else None.
        """
        from odoo import fields
        limit = self._int_param('open_ai_connector.gateway_rate_limit_per_min', '120')
        if limit <= 0:
            return None
        since = fields.Datetime.subtract(fields.Datetime.now(), seconds=60)
        count = request.env['ai.completion.log'].sudo().search_count(
            [('user_id', '=', request.env.uid), ('create_date', '>=', since)])
        if count >= limit:
            return self._json_error("Rate limit exceeded — slow down.",
                                    status=429, etype='rate_limit_error')
        return None

    def _clamp_max_tokens(self, value):
        ceiling = self._int_param('open_ai_connector.gateway_max_tokens', '0')
        if ceiling <= 0:
            return value
        if not value or value > ceiling:
            return ceiling
        return value

    def _resolve_model(self, model_str):
        """Return (provider_record, model_id). Raises ValueError if unresolved."""
        env = request.env
        Provider = env['ai.provider'].sudo()
        if model_str and '/' in model_str:
            head, tail = model_str.split('/', 1)
            provider = Provider._resolve(head)
            if provider:
                return provider, tail
        m = env['ai.model'].sudo().search([('model_id', '=', model_str)], limit=1)
        if m:
            return m.provider_id, model_str
        # fall back to configured default provider
        param = env['ir.config_parameter'].sudo()
        pid = param.get_param('open_ai_connector.default_provider_id')
        if pid:
            provider = Provider.browse(int(pid))
            if provider.exists():
                return provider, (model_str or param.get_param('open_ai_connector.default_model') or '')
        raise ValueError("Could not resolve a provider for model '%s'. "
                         "Use 'provider_code/model_id' or configure a default provider." % model_str)

    # ── endpoints ──────────────────────────────────────────────────────
    @http.route('/ai/v1/chat/completions', type='http', auth='bearer',
                methods=['POST'], csrf=False, save_session=False)
    def chat_completions(self, **kwargs):
        if not self._gateway_enabled():
            return self._json_error("AI gateway is disabled.", status=403)
        denied = self._require_ai_user()
        if denied:
            return denied
        limited = self._rate_limited()
        if limited:
            return limited
        try:
            payload = json.loads(request.httprequest.get_data() or b'{}')
        except (ValueError, TypeError):
            return self._json_error("Invalid JSON body.")

        model_str = payload.get('model')
        messages = payload.get('messages')
        if not model_str or not messages:
            return self._json_error("'model' and 'messages' are required.")

        try:
            provider, model_id = self._resolve_model(model_str)
        except ValueError as exc:
            return self._json_error(str(exc), status=404)

        stream = bool(payload.get('stream'))
        extra = {}
        for k in ('reasoning', 'session_id', 'provider_preferences', 'extra_body'):
            if k in payload:
                extra[k] = payload[k]
        # Don't let caller-supplied extra_body re-inflate cost controls that the
        # gateway clamps (transports do body.update(extra_body) last).
        if isinstance(extra.get('extra_body'), dict):
            for k in ('max_tokens', 'max_completion_tokens', 'n', 'best_of'):
                extra['extra_body'].pop(k, None)

        chat_kwargs = dict(
            provider=provider, model=model_id, messages=messages,
            tools=payload.get('tools'), tool_choice=payload.get('tool_choice'),
            temperature=payload.get('temperature'),
            max_tokens=self._clamp_max_tokens(
                payload.get('max_tokens') or payload.get('max_completion_tokens')),
            extra=extra,
        )

        if stream:
            return self._stream_response(model_str, chat_kwargs)
        return self._sync_response(model_str, chat_kwargs)

    def _sync_response(self, model_str, chat_kwargs):
        from odoo.exceptions import UserError, AccessError
        try:
            result = request.env['ai.connector'].chat(stream=False, **chat_kwargs)
        except AccessError:
            return self._json_error("You are not allowed to use this provider/credential.",
                                    status=403, etype='permission_error')
        except UserError as exc:
            # Log the detail (may contain upstream URLs/bodies) server-side only;
            # return a generic message so the gateway doesn't leak internals.
            _logger.warning("Gateway upstream error: %s", exc)
            return self._json_error("Upstream provider error.", status=502, etype='upstream_error')
        usage = result.get('usage') or {}
        body = {
            'id': 'chatcmpl-' + uuid.uuid4().hex,
            'object': 'chat.completion',
            'created': int(time.time()),
            'model': model_str,
            'choices': [{
                'index': 0,
                'message': {
                    'role': 'assistant',
                    'content': result.get('content'),
                    'tool_calls': result.get('tool_calls'),
                },
                'finish_reason': result.get('finish_reason') or 'stop',
            }],
            'usage': {
                'prompt_tokens': usage.get('prompt_tokens', 0),
                'completion_tokens': usage.get('completion_tokens', 0),
                'total_tokens': usage.get('total_tokens', 0),
            },
        }
        return Response(json.dumps(body), content_type='application/json')

    def _stream_response(self, model_str, chat_kwargs):
        from odoo.exceptions import UserError, AccessError
        cid = 'chatcmpl-' + uuid.uuid4().hex
        created = int(time.time())

        # Build the connector generator NOW (in-request) so credential/provider
        # ORM reads happen while the cursor is open. The returned generator only
        # does network I/O afterwards, which werkzeug streams post-dispatch.
        try:
            connector_gen = request.env['ai.connector'].chat(stream=True, **chat_kwargs)
        except AccessError:
            return self._json_error("You are not allowed to use this provider/credential.",
                                    status=403, etype='permission_error')
        except UserError as exc:
            _logger.warning("Gateway upstream error: %s", exc)
            return self._json_error("Upstream provider error.", status=502, etype='upstream_error')

        def _chunk(delta=None, finish=None):
            data = {
                'id': cid, 'object': 'chat.completion.chunk',
                'created': created, 'model': model_str,
                'choices': [{'index': 0, 'delta': delta or {}, 'finish_reason': finish}],
            }
            return 'data: ' + json.dumps(data) + '\n\n'

        def _generate():
            yield _chunk(delta={'role': 'assistant'})
            finish = 'stop'
            try:
                for piece in connector_gen:
                    if piece.get('delta'):
                        yield _chunk(delta={'content': piece['delta']})
                    if piece.get('done'):
                        finish = piece.get('finish_reason') or 'stop'
            except Exception:  # noqa: BLE001
                _logger.exception("Gateway stream failed")
                yield 'data: ' + json.dumps(
                    {'error': {'message': 'Upstream provider error.'}}) + '\n\n'
            yield _chunk(finish=finish)
            yield 'data: [DONE]\n\n'

        return Response(_generate(), content_type='text/event-stream',
                        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    @http.route('/ai/v1/models', type='http', auth='bearer', methods=['GET'], csrf=False)
    def list_models(self, **kwargs):
        if not self._gateway_enabled():
            return self._json_error("AI gateway is disabled.", status=403)
        denied = self._require_ai_user()
        if denied:
            return denied
        models_recs = request.env['ai.model'].sudo().search([('active', '=', True)])
        data = [{
            'id': f"{m.provider_id.code}/{m.model_id}",
            'object': 'model',
            'owned_by': m.provider_id.code,
        } for m in models_recs]
        return Response(json.dumps({'object': 'list', 'data': data}),
                        content_type='application/json')
