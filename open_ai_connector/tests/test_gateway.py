# -*- coding: utf-8 -*-
import json
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

_CC_RESPONSE = {
    'choices': [{'message': {'content': 'Gateway OK'}, 'finish_reason': 'stop'}],
    'usage': {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5},
}
_PATCH = 'odoo.addons.open_ai_connector.tools.http_client.post_json'


@tagged('post_install', '-at_install')
class TestGateway(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref('base.user_admin')
        cls.provider = cls.env.ref('open_ai_connector.provider_openrouter')
        cls.env['ai.credential'].create({
            'name': 'OpenRouter GW',
            'provider_id': cls.provider.id,
            'api_key': 'sk-gw',
            'is_default': True,
        })
        cls.api_key = cls.env['res.users.apikeys'].with_user(cls.admin)._generate(
            'rpc', 'gw-test', False)

    def test_chat_completions_endpoint(self):
        body = json.dumps({
            'model': 'openrouter/openai/gpt-5',
            'messages': [{'role': 'user', 'content': 'hi'}],
        })
        with patch(_PATCH, return_value=_CC_RESPONSE):
            resp = self.url_open(
                '/ai/v1/chat/completions', data=body,
                headers={'Authorization': f'Bearer {self.api_key}',
                         'Content-Type': 'application/json'})
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload['object'], 'chat.completion')
        self.assertEqual(payload['choices'][0]['message']['content'], 'Gateway OK')
        self.assertEqual(payload['usage']['total_tokens'], 5)

    def test_requires_auth(self):
        body = json.dumps({'model': 'openrouter/x', 'messages': [{'role': 'user', 'content': 'hi'}]})
        resp = self.url_open('/ai/v1/chat/completions', data=body,
                             headers={'Content-Type': 'application/json'})
        self.assertIn(resp.status_code, (401, 403))

    def test_models_endpoint(self):
        self.env['ai.model'].create({
            'provider_id': self.provider.id, 'model_id': 'openai/gpt-5'})
        resp = self.url_open('/ai/v1/models',
                             headers={'Authorization': f'Bearer {self.api_key}'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['object'], 'list')
        self.assertTrue(any(m['id'] == 'openrouter/openai/gpt-5' for m in data['data']))
