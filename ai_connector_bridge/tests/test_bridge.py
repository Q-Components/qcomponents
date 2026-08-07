# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.ai_connector_bridge.utils import bridge


@tagged('post_install', '-at_install')
class TestBridge(TransactionCase):

    def test_patch_applied(self):
        # post_load monkeypatch must be active on the LLMApiService class.
        from odoo.addons.ai.utils.llm_api_service import LLMApiService
        self.assertTrue(getattr(LLMApiService, '_oconn_patched', False))
        self.assertTrue(hasattr(LLMApiService, '_oconn_orig_request_llm'))

    def test_route_off_by_default(self):
        self.env['ir.config_parameter'].sudo().set_param('ai_connector_bridge.enabled', 'False')
        self.assertIsNone(bridge.route(self.env, 'gpt-4o'))

    def test_route_oconn_prefix_forces_routing(self):
        self.assertEqual(bridge.route(self.env, 'oconn:xai/grok-4'), ('xai', 'grok-4', None))

    def test_route_uses_bridge_settings_with_credential(self):
        prov = self.env.ref('open_ai_connector.provider_xai')
        cred = self.env['ai.credential'].create({'name': 'acct', 'provider_id': prov.id})
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('ai_connector_bridge.enabled', 'True')
        icp.set_param('ai_connector_bridge.provider_id', str(prov.id))
        icp.set_param('ai_connector_bridge.model', 'grok-4')
        icp.set_param('ai_connector_bridge.credential_id', str(cred.id))
        try:
            self.assertEqual(bridge.route(self.env, 'gpt-4o'), ('xai', 'grok-4', cred.id))
            # bridge provider/model blank -> falls back to the gateway default
            icp.set_param('ai_connector_bridge.provider_id', '')
            icp.set_param('ai_connector_bridge.model', '')
            icp.set_param('open_ai_connector.default_provider_id', str(prov.id))
            icp.set_param('open_ai_connector.default_model', 'grok-2')
            self.assertEqual(bridge.route(self.env, 'gpt-4o')[:2], ('xai', 'grok-2'))
            # enabled but nothing resolvable -> no routing (don't break stock AI)
            icp.set_param('open_ai_connector.default_model', '')
            self.assertIsNone(bridge.route(self.env, 'gpt-4o'))
        finally:
            for k in ('ai_connector_bridge.enabled', 'ai_connector_bridge.provider_id',
                      'ai_connector_bridge.model', 'ai_connector_bridge.credential_id'):
                icp.set_param(k, '')

    def test_request_via_connector_passes_credential(self):
        class _Svc:
            def __init__(self, env):
                self.env = env
        svc = _Svc(self.env)
        cap = {}

        def fake_chat(self, provider, model, messages, **kw):
            cap['credential'] = kw.get('credential')
            return {'content': 'ok', 'tool_calls': []}
        with patch.object(type(self.env['ai.connector']), 'chat', fake_chat):
            bridge.request_via_connector(svc, 'xai', 'grok-4', 'gpt-4o', ['s'], [],
                                         inputs=[{'role': 'user', 'content': 'hi'}],
                                         credential_id=77)
        self.assertEqual(cap['credential'], 77)

    def test_build_messages_translates_inputs_and_files(self):
        msgs = bridge.build_messages(['be terse'], [], None, [{'role': 'user', 'content': 'hi'}])
        self.assertEqual(msgs[0], {'role': 'system', 'content': 'be terse'})
        self.assertEqual(msgs[-1], {'role': 'user', 'content': 'hi'})
        # an image file becomes an OpenAI multimodal image part on a user msg
        m = bridge.build_messages([], ['look'], [{'mimetype': 'image/png', 'value': 'QUJD'}], [])
        user = m[-1]
        self.assertEqual(user['role'], 'user')
        self.assertTrue(any(p.get('type') == 'image_url' for p in user['content']))

    def test_inputs_function_call_roundtrip(self):
        ins = [{'type': 'function_call', 'name': 'f', 'arguments': '{"a":1}', 'call_id': 'c1'},
               {'type': 'function_call_output', 'call_id': 'c1', 'output': '42'}]
        m = bridge._inputs_to_messages(ins)
        self.assertEqual(m[0]['role'], 'assistant')
        self.assertEqual(m[0]['tool_calls'][0]['function']['name'], 'f')
        self.assertEqual(m[1], {'role': 'tool', 'tool_call_id': 'c1', 'content': '42'})

    def test_tools_to_openai(self):
        tools = {'add': ('adds two numbers', True, lambda **k: ('ok', None),
                         {'type': 'object', 'properties': {'a': {'type': 'integer'}}})}
        out = bridge.tools_to_openai(tools)
        self.assertEqual(out[0]['type'], 'function')
        self.assertEqual(out[0]['function']['name'], 'add')
        self.assertEqual(out[0]['function']['description'], 'adds two numbers')

    def test_request_via_connector_text(self):
        class _Svc:
            def __init__(self, env):
                self.env = env
        svc = _Svc(self.env)
        with patch.object(type(self.env['ai.connector']), 'chat',
                          return_value={'content': 'hello', 'tool_calls': []}):
            resp, to_call, nin = bridge.request_via_connector(
                svc, 'xai', 'grok-4', 'gpt-4o', ['sys'], [],
                inputs=[{'role': 'user', 'content': 'hi'}])
        self.assertEqual(resp, ['hello'])
        self.assertEqual(to_call, [])

    def test_request_via_connector_toolcall_shapes(self):
        class _Svc:
            def __init__(self, env):
                self.env = env
        svc = _Svc(self.env)
        tc = [{'id': 'c1', 'type': 'function',
               'function': {'name': 'f', 'arguments': '{"a":1}'}}]
        with patch.object(type(self.env['ai.connector']), 'chat',
                          return_value={'content': None, 'tool_calls': tc}):
            resp, to_call, nin = bridge.request_via_connector(
                svc, 'xai', 'grok-4', 'gpt-4o', ['sys'], [], inputs=[])
        self.assertEqual(resp, [])                       # text gated when tool calls present
        self.assertEqual(to_call, [('f', 'c1', {'a': 1})])
        self.assertEqual(nin[-1], {'type': 'function_call', 'name': 'f',
                                   'arguments': '{"a":1}', 'call_id': 'c1'})
