# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.open_ai_connector.tools.transport_base import RequestContext, get_transport
from odoo.addons.open_ai_connector.tools import anthropic as anthropic_t


@tagged('post_install', '-at_install')
class TestTransports(TransactionCase):

    def _ctx(self, **kw):
        defaults = dict(model='gpt-4o-mini', messages=[{'role': 'user', 'content': 'hi'}],
                        provider={'code': 'x', 'api_mode': 'chat_completions'},
                        base_url='https://api.example.com/v1')
        defaults.update(kw)
        return RequestContext(**defaults)

    # ── chat_completions ────────────────────────────────────────────
    def test_cc_build_body_max_completion_tokens(self):
        t = get_transport('chat_completions')
        body = t.build_body(self._ctx(model='gpt-4o', max_tokens=100))
        self.assertEqual(body['model'], 'gpt-4o')
        self.assertIn('max_completion_tokens', body)
        self.assertNotIn('max_tokens', body)

    def test_cc_build_body_plain_max_tokens(self):
        t = get_transport('chat_completions')
        body = t.build_body(self._ctx(model='deepseek-chat', max_tokens=50, temperature=0.5))
        self.assertEqual(body['max_tokens'], 50)
        self.assertEqual(body['temperature'], 0.5)

    def test_cc_omit_temperature(self):
        t = get_transport('chat_completions')
        ctx = self._ctx(temperature=0.9,
                        provider={'code': 'kimi-coding', 'api_mode': 'chat_completions',
                                  'omit_temperature': True})
        body = t.build_body(ctx)
        self.assertNotIn('temperature', body)

    def test_cc_parse_response(self):
        t = get_transport('chat_completions')
        raw = {'choices': [{'message': {'content': 'Hello!'}, 'finish_reason': 'stop'}],
               'usage': {'prompt_tokens': 5, 'completion_tokens': 2, 'total_tokens': 7}}
        nr = t.parse_response(raw, self._ctx())
        self.assertEqual(nr.content, 'Hello!')
        self.assertEqual(nr.finish_reason, 'stop')
        self.assertEqual(nr.usage.total_tokens, 7)

    def test_cc_parse_tool_calls(self):
        t = get_transport('chat_completions')
        raw = {'choices': [{'message': {'content': None, 'tool_calls': [
            {'id': 'call_1', 'function': {'name': 'get_weather', 'arguments': '{"city":"NYC"}'}}]},
            'finish_reason': 'tool_calls'}]}
        nr = t.parse_response(raw, self._ctx())
        self.assertEqual(nr.finish_reason, 'tool_calls')
        self.assertEqual(len(nr.tool_calls), 1)
        self.assertEqual(nr.tool_calls[0].name, 'get_weather')

    # ── anthropic ───────────────────────────────────────────────────
    def test_anthropic_convert_messages_system_and_vision(self):
        messages = [
            {'role': 'system', 'content': 'You are helpful.'},
            {'role': 'user', 'content': [
                {'type': 'text', 'text': 'What is this?'},
                {'type': 'image_url',
                 'image_url': {'url': 'data:image/png;base64,AAAA'}}]},
        ]
        system, amsgs = anthropic_t.convert_messages_to_anthropic(messages)
        self.assertEqual(system, 'You are helpful.')
        self.assertEqual(amsgs[0]['role'], 'user')
        types = [b['type'] for b in amsgs[0]['content']]
        self.assertIn('text', types)
        self.assertIn('image', types)

    def test_anthropic_build_body_requires_max_tokens(self):
        t = get_transport('anthropic_messages')
        ctx = self._ctx(provider={'code': 'anthropic', 'api_mode': 'anthropic_messages'},
                        messages=[{'role': 'user', 'content': 'hi'}])
        body = t.build_body(ctx)
        self.assertIn('max_tokens', body)
        self.assertEqual(body['model'], ctx.model)

    def test_anthropic_parse_response(self):
        t = get_transport('anthropic_messages')
        raw = {'content': [{'type': 'text', 'text': 'Hi there'}],
               'stop_reason': 'end_turn',
               'usage': {'input_tokens': 10, 'output_tokens': 3}}
        nr = t.parse_response(raw, self._ctx())
        self.assertEqual(nr.content, 'Hi there')
        self.assertEqual(nr.finish_reason, 'stop')
        self.assertEqual(nr.usage.prompt_tokens, 10)

    def test_anthropic_tool_use(self):
        t = get_transport('anthropic_messages')
        raw = {'content': [{'type': 'tool_use', 'id': 'tu_1', 'name': 'f', 'input': {'a': 1}}],
               'stop_reason': 'tool_use'}
        nr = t.parse_response(raw, self._ctx())
        self.assertEqual(nr.finish_reason, 'tool_calls')
        self.assertEqual(nr.tool_calls[0].name, 'f')

    # ── codex_responses ─────────────────────────────────────────────
    def test_codex_build_body(self):
        t = get_transport('codex_responses')
        ctx = self._ctx(provider={'code': 'xai', 'api_mode': 'codex_responses'},
                        messages=[{'role': 'system', 'content': 'sys'},
                                  {'role': 'user', 'content': 'hi'}])
        body = t.build_body(ctx)
        self.assertEqual(body['instructions'], 'sys')
        self.assertTrue(isinstance(body['input'], list))

    def test_codex_build_body_always_has_instructions(self):
        # The Codex /responses backend rejects requests without instructions
        # ("HTTP 400: Instructions are required"). With no system message we
        # must still send a non-empty default.
        from odoo.addons.open_ai_connector.tools.codex_responses import DEFAULT_INSTRUCTIONS
        t = get_transport('codex_responses')
        ctx = self._ctx(provider={'code': 'openai-codex', 'api_mode': 'codex_responses'},
                        messages=[{'role': 'user', 'content': 'ping'}])
        body = t.build_body(ctx)
        self.assertTrue(body.get('instructions'))
        self.assertEqual(body['instructions'], DEFAULT_INSTRUCTIONS)

    def test_codex_parse_response(self):
        t = get_transport('codex_responses')
        raw = {'output': [{'type': 'message',
                           'content': [{'type': 'output_text', 'text': 'done'}]}],
               'usage': {'input_tokens': 4, 'output_tokens': 1}}
        nr = t.parse_response(raw, self._ctx())
        self.assertEqual(nr.content, 'done')
        self.assertEqual(nr.usage.total_tokens, 5)

    def test_codex_backend_complete_streams_and_aggregates(self):
        # The ChatGPT Codex backend rejects non-streaming requests; complete()
        # must stream and aggregate (not call post_json).
        t = get_transport('codex_responses')
        ctx = self._ctx(
            provider={'code': 'openai-codex', 'api_mode': 'codex_responses',
                      'base_url': 'https://chatgpt.com/backend-api/codex'},
            base_url='https://chatgpt.com/backend-api/codex',
            messages=[{'role': 'user', 'content': 'ping'}])
        events = [
            {'type': 'response.output_text.delta', 'delta': 'po'},
            {'type': 'response.output_text.delta', 'delta': 'ng'},
            {'type': 'response.completed',
             'response': {'usage': {'input_tokens': 2, 'output_tokens': 1}}},
        ]
        with patch('odoo.addons.open_ai_connector.tools.http_client.post_sse',
                   return_value=iter(events)) as mock_sse, \
             patch('odoo.addons.open_ai_connector.tools.http_client.post_json') as mock_json:
            nr = t.complete(ctx)
        self.assertTrue(mock_sse.called)
        self.assertFalse(mock_json.called)   # never non-streamed for codex backend
        self.assertEqual(nr.content, 'pong')
        self.assertEqual(nr.usage.total_tokens, 3)

    def test_codex_backend_omits_max_output_tokens(self):
        # ChatGPT Codex backend rejects max_output_tokens; xAI accepts it.
        t = get_transport('codex_responses')
        codex_ctx = self._ctx(
            provider={'code': 'openai-codex', 'api_mode': 'codex_responses',
                      'base_url': 'https://chatgpt.com/backend-api/codex'},
            base_url='https://chatgpt.com/backend-api/codex', max_tokens=16)
        self.assertNotIn('max_output_tokens', t.build_body(codex_ctx))
        xai_ctx = self._ctx(provider={'code': 'xai', 'api_mode': 'codex_responses',
                                      'base_url': 'https://api.x.ai/v1'},
                            base_url='https://api.x.ai/v1', max_tokens=16)
        self.assertEqual(t.build_body(xai_ctx).get('max_output_tokens'), 16)

    def test_codex_xai_complete_stays_non_streaming(self):
        # xAI's /responses supports non-streaming; complete() must NOT stream.
        t = get_transport('codex_responses')
        ctx = self._ctx(provider={'code': 'xai', 'api_mode': 'codex_responses',
                                  'base_url': 'https://api.x.ai/v1'},
                        base_url='https://api.x.ai/v1')
        raw = {'output': [{'type': 'message',
                           'content': [{'type': 'output_text', 'text': 'hi'}]}]}
        with patch('odoo.addons.open_ai_connector.tools.http_client.post_json',
                   return_value=raw) as mock_json, \
             patch('odoo.addons.open_ai_connector.tools.http_client.post_sse') as mock_sse:
            nr = t.complete(ctx)
        self.assertTrue(mock_json.called)
        self.assertFalse(mock_sse.called)
        self.assertEqual(nr.content, 'hi')
