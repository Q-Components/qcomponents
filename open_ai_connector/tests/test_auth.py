# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged

from odoo.addons.open_ai_connector.tools import auth
from odoo.addons.open_ai_connector.tools.http_client import AiHttpError


@tagged('post_install', '-at_install')
class TestAuth(TransactionCase):

    def test_api_key_bearer(self):
        provider = {'api_mode': 'chat_completions', 'auth_type': 'api_key',
                    'base_url': 'https://api.example.com/v1'}
        cred = {'api_key': 'sk-test'}
        resolved = auth.resolve(provider, cred)
        self.assertEqual(resolved['headers']['Authorization'], 'Bearer sk-test')
        self.assertEqual(resolved['base_url'], 'https://api.example.com/v1')

    def test_anthropic_x_api_key(self):
        provider = {'api_mode': 'anthropic_messages', 'auth_type': 'api_key',
                    'base_url': 'https://api.anthropic.com'}
        resolved = auth.resolve(provider, {'api_key': 'sk-ant'})
        self.assertEqual(resolved['headers']['x-api-key'], 'sk-ant')
        self.assertEqual(resolved['headers']['anthropic-version'], auth.ANTHROPIC_VERSION)
        self.assertNotIn('Authorization', resolved['headers'])

    def test_oauth_bearer(self):
        provider = {'api_mode': 'chat_completions', 'auth_type': 'oauth_external',
                    'base_url': 'https://portal.example.com/v1'}
        resolved = auth.resolve(provider, {'oauth_access_token': 'tok-123'})
        self.assertEqual(resolved['headers']['Authorization'], 'Bearer tok-123')

    def test_copilot_headers(self):
        provider = {'api_mode': 'chat_completions', 'auth_type': 'copilot',
                    'base_url': 'https://api.githubcopilot.com'}
        resolved = auth.resolve(provider, {'api_key': 'gho_x'})
        self.assertEqual(resolved['headers']['Authorization'], 'Bearer gho_x')
        self.assertIn('Copilot-Integration-Id', resolved['headers'])

    def test_base_url_override(self):
        provider = {'api_mode': 'chat_completions', 'auth_type': 'api_key', 'base_url': ''}
        resolved = auth.resolve(provider, {'api_key': 'k', 'base_url': 'http://localhost:11434/v1'})
        self.assertEqual(resolved['base_url'], 'http://localhost:11434/v1')

    def test_external_process_raises(self):
        provider = {'api_mode': 'chat_completions', 'auth_type': 'external_process'}
        with self.assertRaises(AiHttpError):
            auth.resolve(provider, {})

    def test_missing_token_raises(self):
        provider = {'api_mode': 'chat_completions', 'auth_type': 'api_key', 'base_url': 'x'}
        with self.assertRaises(AiHttpError):
            auth.resolve(provider, {})
