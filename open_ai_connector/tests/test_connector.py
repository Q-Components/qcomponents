# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError

from odoo.addons.open_ai_connector.tools.http_client import AiHttpError

_CC_RESPONSE = {
    'choices': [{'message': {'content': 'Hello from the connector!'}, 'finish_reason': 'stop'}],
    'usage': {'prompt_tokens': 8, 'completion_tokens': 4, 'total_tokens': 12},
}
_PATCH = 'odoo.addons.open_ai_connector.tools.http_client.post_json'


@tagged('post_install', '-at_install')
class TestConnector(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env.ref('open_ai_connector.provider_openrouter')
        cls.cred = cls.env['ai.credential'].create({
            'name': 'OpenRouter Test',
            'provider_id': cls.provider.id,
            'api_key': 'sk-test-key',
            'is_default': True,
        })

    def test_chat_happy_path(self):
        with patch(_PATCH, return_value=_CC_RESPONSE) as mock_post:
            result = self.env['ai.connector'].chat(
                provider='openrouter', model='openai/gpt-5',
                messages=[{'role': 'user', 'content': 'hi'}])
        self.assertEqual(result['content'], 'Hello from the connector!')
        self.assertEqual(result['usage']['total_tokens'], 12)
        # endpoint + bearer header were used
        args, kwargs = mock_post.call_args
        self.assertTrue(args[0].endswith('/chat/completions'))
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer sk-test-key')

    def test_chat_text_convenience(self):
        with patch(_PATCH, return_value=_CC_RESPONSE):
            text = self.env['ai.connector'].chat_text(
                'openrouter', 'openai/gpt-5', [{'role': 'user', 'content': 'hi'}])
        self.assertEqual(text, 'Hello from the connector!')

    def test_chat_logs_usage(self):
        Log = self.env['ai.completion.log']
        before = Log.search_count([])
        with patch(_PATCH, return_value=_CC_RESPONSE):
            self.env['ai.connector'].chat(
                provider=self.provider, model='openai/gpt-5',
                messages=[{'role': 'user', 'content': 'hi'}])
        self.assertEqual(Log.search_count([]), before + 1)
        log = Log.search([], order='id desc', limit=1)
        self.assertEqual(log.status, 'ok')
        self.assertEqual(log.total_tokens, 12)

    def test_chat_error_raises_usererror(self):
        with patch(_PATCH, side_effect=AiHttpError(401, 'Unauthorized')):
            with self.assertRaises(UserError):
                self.env['ai.connector'].chat(
                    provider='openrouter', model='openai/gpt-5',
                    messages=[{'role': 'user', 'content': 'hi'}], log=False)

    def test_unknown_provider(self):
        with self.assertRaises(UserError):
            self.env['ai.connector'].chat(
                provider='does-not-exist', model='x',
                messages=[{'role': 'user', 'content': 'hi'}])

    def test_not_wired_provider(self):
        acp = self.env.ref('open_ai_connector.provider_copilot_acp')
        self.env['ai.credential'].create({
            'name': 'ACP', 'provider_id': acp.id, 'is_default': True})
        with self.assertRaises(UserError):
            self.env['ai.connector'].chat(
                provider='copilot-acp', model='x',
                messages=[{'role': 'user', 'content': 'hi'}])

    def test_resolve_alias(self):
        # 'or' is an alias of openrouter
        with patch(_PATCH, return_value=_CC_RESPONSE):
            result = self.env['ai.connector'].chat(
                provider='or', model='openai/gpt-5',
                messages=[{'role': 'user', 'content': 'hi'}])
        self.assertEqual(result['content'], 'Hello from the connector!')

    def test_oauth_wizard_missing_config_raises_usererror(self):
        # An OAuth provider with NO endpoints + clicking Start must raise a
        # friendly UserError, not a raw AiHttpError/RPC error.
        prov = self.env['ai.provider'].create({
            'name': 'Bare OAuth', 'code': 'test-bare-oauth', 'auth_type': 'oauth_external'})
        cred = self.env['ai.credential'].create({
            'name': 'Bare', 'provider_id': prov.id})
        wiz = self.env['ai.oauth.wizard'].create({'credential_id': cred.id})
        with self.assertRaises(UserError):
            wiz.action_start()

    def test_credential_inherits_provider_oauth_defaults(self):
        # OAuth providers carry seeded endpoints; a credential inherits them so
        # the user never has to type the client id / URLs.
        codex = self.env.ref('open_ai_connector.provider_openai_codex')
        cred = self.env['ai.credential'].create({
            'name': 'Codex', 'provider_id': codex.id})
        d = cred._as_cred_dict()
        self.assertEqual(d['oauth_client_id'], 'app_EMoamEEZ73f0CkXaXp7hrann')
        self.assertTrue(d['oauth_token_url'])
        # Codex now uses the standard PKCE flow (form-encoded token endpoint);
        # the token URL must be the exchange endpoint, not the poll endpoint.
        self.assertEqual(d['oauth_flavor'], 'standard')
        self.assertEqual(d['oauth_auth_url'], 'https://auth.openai.com/oauth/authorize')
        self.assertEqual(d['oauth_redirect_uri'], 'http://localhost:1455/auth/callback')
        self.assertTrue(d['oauth_token_url'].endswith('/oauth/token'))

    def test_xai_oauth_provider_seeded(self):
        # xAI Grok OAuth (SuperGrok/Premium+) — separate from the api_key 'xai'.
        prov = self.env.ref('open_ai_connector.provider_xai_oauth')
        self.assertEqual(prov.code, 'xai-oauth')
        self.assertEqual(prov.auth_type, 'oauth_external')
        self.assertEqual(prov.api_mode, 'codex_responses')
        d = self.env['ai.credential'].create(
            {'name': 'Grok OAuth', 'provider_id': prov.id})._as_cred_dict()
        self.assertEqual(d['oauth_client_id'], 'b1a00492-073a-47ea-816f-4c329264a828')
        self.assertEqual(d['oauth_auth_url'], 'https://auth.x.ai/oauth2/authorize')
        self.assertEqual(d['oauth_token_url'], 'https://auth.x.ai/oauth2/token')

    def test_nous_provider_removed(self):
        self.assertFalse(self.env['ai.provider'].search([('code', '=', 'nous')]))

    def test_popular_providers_sort_first(self):
        # Curated display order: flagship providers carry low sequences and must
        # sort ahead of the long tail (sequence 500) and the unwired ACP (900).
        Provider = self.env['ai.provider']
        seq = {p.code: p.sequence
               for p in Provider.search([('code', 'in', (
                   'openai-codex', 'anthropic', 'gemini', 'xai',
                   'arcee', 'azure-foundry', 'copilot-acp'))])}
        self.assertEqual(seq['openai-codex'], 10)
        self.assertEqual(seq['anthropic'], 20)
        self.assertEqual(seq['gemini'], 30)
        # flagship < long tail < unwired
        self.assertLess(seq['xai'], seq['arcee'])
        self.assertLess(seq['arcee'], seq['copilot-acp'])
        # first record by the model's _order is the top flagship
        self.assertEqual(Provider.search([], limit=1).code, 'openai-codex')

    def test_playground_default_model_skips_review_model(self):
        # Selecting a provider must auto-fill a real chat model, not the catalog's
        # alphabetical-first entry (codex 'codex-auto-review' is review-only).
        prov = self.env.ref('open_ai_connector.provider_openai_codex')
        wiz = self.env['ai.playground'].new({'provider_id': prov.id})
        wiz._onchange_provider()
        # codex has no default_aux_model -> first fallback model wins.
        self.assertEqual(wiz.model, 'gpt-5.5')
        self.assertNotEqual(wiz.model, 'codex-auto-review')

    def test_settings_default_model_picker_roundtrips(self):
        # The Default Model picker (ai.model M2o) must persist as the plain
        # model-id string the gateway reads, and resolve back on reload.
        prov = self.env.ref('open_ai_connector.provider_openai_codex')
        model = self.env['ai.model'].create(
            {'provider_id': prov.id, 'model_id': 'gpt-5.5', 'name': 'gpt-5.5'})
        Settings = self.env['res.config.settings']
        Settings.create({'ai_default_provider_id': prov.id,
                         'ai_default_model_id': model.id}).set_values()
        icp = self.env['ir.config_parameter'].sudo()
        self.assertEqual(icp.get_param('open_ai_connector.default_model'), 'gpt-5.5')
        # get_values resolves the stored id string back to the catalog record.
        self.assertEqual(Settings.get_values().get('ai_default_model_id'), model.id)

    def test_gemini_cli_fetch_uses_fallback_models(self):
        # Gemini CLI's base_url is the cloudcode-pa:// internal scheme (no REST
        # /models), so Fetch Models must fall back to the curated list, not 0.
        prov = self.env.ref('open_ai_connector.provider_google_gemini_cli')
        cred = self.env['ai.credential'].create(
            {'name': 'Gemini CLI', 'provider_id': prov.id})
        added, total = prov._fetch_models_with_credential(cred)  # no network: non-HTTP base
        self.assertEqual(total, 4)
        self.assertIn('gemini-3-flash-preview', prov.model_ids.mapped('model_id'))

    # ── Gemini CLI: Cloud Code Assist chat transport ──────────────────────
    def test_gemini_cli_uses_cloudcode_transport(self):
        prov = self.env.ref('open_ai_connector.provider_google_gemini_cli')
        self.assertEqual(prov.api_mode, 'gemini_cloudcode')
        self.assertTrue(prov.is_wired)
        from odoo.addons.open_ai_connector.tools.transport_base import get_transport
        self.assertEqual(get_transport('gemini_cloudcode').api_mode, 'gemini_cloudcode')

    def test_gemini_cloudcode_request_and_response(self):
        """chat() builds the Code Assist envelope and parses a Gemini response,
        without ever hitting the OpenAI /chat/completions path."""
        from datetime import datetime, timedelta
        prov = self.env.ref('open_ai_connector.provider_google_gemini_cli')
        cred = self.env['ai.credential'].create({
            'name': 'Gemini CLI Chat', 'provider_id': prov.id,
            'oauth_access_token': 'ya29.test-token',
            'oauth_token_expiry': datetime.utcnow() + timedelta(hours=1),
            'gemini_project_id': 'my-gcp-project',  # set => skip discovery
            'is_default': True,
        })
        gemini_reply = {'response': {'candidates': [{'content': {'parts': [
            {'text': 'Hi from Gemini CLI!'}]}, 'finishReason': 'STOP'}],
            'usageMetadata': {'promptTokenCount': 5, 'candidatesTokenCount': 3,
                              'totalTokenCount': 8}}}
        with patch(_PATCH, return_value=gemini_reply) as mock_post:
            result = self.env['ai.connector'].chat(
                provider='google-gemini-cli', model='gemini-3-flash-preview',
                messages=[{'role': 'system', 'content': 'be brief'},
                          {'role': 'user', 'content': 'hello'}],
                credential=cred.id, temperature=0.4, max_tokens=128)
        self.assertEqual(result['content'], 'Hi from Gemini CLI!')
        self.assertEqual(result['usage']['total_tokens'], 8)
        url, kwargs = mock_post.call_args[0][0], mock_post.call_args[1]
        self.assertTrue(url.endswith('/v1internal:generateContent'))
        self.assertTrue(url.startswith('https://cloudcode-pa.googleapis.com'))
        # envelope shape + translated contents
        body = kwargs['json_body']
        self.assertEqual(body['project'], 'my-gcp-project')
        self.assertEqual(body['model'], 'gemini-3-flash-preview')
        self.assertEqual(body['request']['systemInstruction']['parts'][0]['text'], 'be brief')
        self.assertEqual(body['request']['contents'][0]['role'], 'user')
        self.assertEqual(body['request']['generationConfig']['maxOutputTokens'], 128)
        # bearer carried from the resolved OAuth token
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer ya29.test-token')

    def test_gemini_cloudcode_tool_call_parsing(self):
        from odoo.addons.open_ai_connector.tools import gemini_cloudcode
        from odoo.addons.open_ai_connector.tools.transport_base import RequestContext
        payload = {'response': {'candidates': [{'content': {'parts': [
            {'functionCall': {'name': 'get_weather', 'args': {'city': 'Paris'}}}]},
            'finishReason': 'STOP'}]}}
        nr = gemini_cloudcode.parse_gemini_response(payload, RequestContext(model='m', messages=[]))
        self.assertEqual(nr.finish_reason, 'tool_calls')
        self.assertEqual(nr.tool_calls[0].name, 'get_weather')
        self.assertEqual(nr.tool_calls[0].parsed_arguments(), {'city': 'Paris'})

    # ── Codex: Cloudflare originator + ChatGPT-Account-ID headers ──
    def test_codex_cloudflare_and_account_headers(self):
        import base64 as _b64
        from odoo.addons.open_ai_connector.tools import codex_responses

        def _jwt(claims):
            enc = lambda o: _b64.urlsafe_b64encode(  # noqa: E731
                __import__('json').dumps(o).encode()).rstrip(b'=').decode()
            return '%s.%s.sig' % (enc({'alg': 'none'}), enc(claims))

        token = _jwt({'https://api.openai.com/auth': {'chatgpt_account_id': 'acct-xyz'}})
        h = codex_responses._codex_cloudflare_headers('Bearer ' + token)
        self.assertEqual(h['originator'], 'codex_cli_rs')
        self.assertTrue(h['User-Agent'].startswith('codex_cli_rs/'))
        self.assertEqual(h['ChatGPT-Account-ID'], 'acct-xyz')
        # malformed token: keep the Cloudflare headers, drop the account id
        h2 = codex_responses._codex_cloudflare_headers('Bearer not-a-jwt')
        self.assertEqual(h2['originator'], 'codex_cli_rs')
        self.assertNotIn('ChatGPT-Account-ID', h2)

    def test_codex_chat_sends_cloudflare_headers(self):
        import base64 as _b64
        from datetime import datetime, timedelta

        def _jwt(claims):
            enc = lambda o: _b64.urlsafe_b64encode(  # noqa: E731
                __import__('json').dumps(o).encode()).rstrip(b'=').decode()
            return '%s.%s.sig' % (enc({'alg': 'none'}), enc(claims))

        prov = self.env.ref('open_ai_connector.provider_openai_codex')
        token = _jwt({'https://api.openai.com/auth': {'chatgpt_account_id': 'acct-1'}})
        cred = self.env['ai.credential'].create({
            'name': 'Codex', 'provider_id': prov.id,
            'oauth_access_token': token,
            'oauth_token_expiry': datetime.utcnow() + timedelta(hours=1),
            'is_default': True})
        captured = {}

        def fake_sse(url, headers=None, json_body=None, timeout=None,
                     proxy_url=None, impersonate=None):
            captured['headers'] = headers
            captured['impersonate'] = impersonate
            yield {'type': 'response.output_text.delta', 'delta': 'ok'}
            yield {'type': 'response.completed',
                   'response': {'usage': {'input_tokens': 1, 'output_tokens': 1}}}

        with patch('odoo.addons.open_ai_connector.tools.http_client.post_sse',
                   side_effect=fake_sse):
            result = self.env['ai.connector'].chat(
                provider='openai-codex', model='gpt-5.5-codex',
                messages=[{'role': 'user', 'content': 'hi'}], credential=cred.id)
        self.assertEqual(result['content'], 'ok')
        self.assertEqual(captured['headers']['originator'], 'codex_cli_rs')
        self.assertEqual(captured['impersonate'], 'chrome')  # Codex backend uses uTLS too
        self.assertEqual(captured['headers']['ChatGPT-Account-ID'], 'acct-1')

    # ── OAuth refresh: race-safe + proactive cron ─────
    def test_oauth_refresh_reactive_and_fresh_skip(self):
        from datetime import datetime, timedelta
        prov = self.env.ref('open_ai_connector.provider_openai_codex')
        cred = self.env['ai.credential'].create({
            'name': 'Codex refresh', 'provider_id': prov.id,
            'oauth_access_token': 'old', 'oauth_refresh_token': 'r0',
            'oauth_token_expiry': datetime.utcnow() - timedelta(minutes=1)})  # stale
        with patch('odoo.addons.open_ai_connector.tools.http_client.post_form',
                   return_value={'access_token': 'new', 'refresh_token': 'r1',
                                 'expires_in': 3600}) as mock_form:
            cred._ensure_oauth_fresh()
        self.assertEqual(cred.sudo().oauth_access_token, 'new')
        self.assertEqual(cred.sudo().oauth_refresh_token, 'r1')  # rotation persisted
        self.assertTrue(mock_form.called)
        # now fresh: a second call must NOT hit the network
        with patch('odoo.addons.open_ai_connector.tools.http_client.post_form',
                   side_effect=AssertionError('should not refresh a fresh token')):
            cred._ensure_oauth_fresh()

    def test_cron_proactive_refresh(self):
        from datetime import datetime, timedelta
        prov = self.env.ref('open_ai_connector.provider_openai_codex')
        cred = self.env['ai.credential'].create({
            'name': 'Codex cron', 'provider_id': prov.id,
            'oauth_access_token': 'old', 'oauth_refresh_token': 'r0',
            'oauth_token_expiry': datetime.utcnow() + timedelta(minutes=5)})  # within 15m lead
        with patch('odoo.addons.open_ai_connector.tools.http_client.post_form',
                   return_value={'access_token': 'fresh', 'expires_in': 3600}):
            n = self.env['ai.credential']._cron_refresh_oauth_tokens(lead_seconds=900)
        self.assertGreaterEqual(n, 1)
        self.assertEqual(cred.sudo().oauth_access_token, 'fresh')

    def test_gemini_cloudcode_project_discovery_and_cache(self):
        """No configured project => discover via loadCodeAssist, then cache it."""
        from odoo.addons.open_ai_connector.tools import gemini_cloudcode
        prov = self.env.ref('open_ai_connector.provider_google_gemini_cli')
        cred = self.env['ai.credential'].create(
            {'name': 'Gemini CLI Disc', 'provider_id': prov.id})
        load_reply = {'currentTier': {'id': 'free-tier'},
                      'cloudaicompanionProject': 'discovered-proj'}
        with patch('odoo.addons.open_ai_connector.tools.http_client.post_json',
                   return_value=load_reply) as mock_post:
            project = cred._ensure_gemini_project('ya29.tok')
        self.assertEqual(project, 'discovered-proj')
        self.assertTrue(mock_post.call_args[0][0].endswith(':loadCodeAssist'))
        # cached on the credential => a second call does no network
        with patch('odoo.addons.open_ai_connector.tools.http_client.post_json',
                   side_effect=AssertionError('should not re-discover')):
            self.assertEqual(cred._ensure_gemini_project('ya29.tok'), 'discovered-proj')

    # ── allowlist auto-includes configured provider endpoints ─────────────
    def test_allowlist_includes_configured_provider_endpoints(self):
        from odoo.addons.open_ai_connector.tools import http_client, url_guard
        icp = self.env['ir.config_parameter'].sudo()
        codex = self.env.ref('open_ai_connector.provider_openai_codex')
        self.env['ai.credential'].create({'name': 'Codex', 'provider_id': codex.id})
        icp.set_param('open_ai_connector.outbound_host_allowlist', 'example.com')
        try:
            self.env['ai.connector']._apply_outbound_policy()
            _bp, allow = http_client._get_policy()
            self.assertIn('example.com', allow)        # admin entry preserved
            self.assertIn('auth.openai.com', allow)    # provider OAuth host auto-added
            self.assertIn('chatgpt.com', allow)        # provider base/models host
            # the OAuth token exchange that was being blocked now passes
            url_guard.validate_outbound_url(
                'https://auth.openai.com/oauth/token', allowlist=allow)
            # an unrelated host is still refused
            with self.assertRaises(AiHttpError):
                url_guard.validate_outbound_url('https://evil.example.net/x', allowlist=allow)
            # internal/metadata stays blocked even though it's "a host"
            with self.assertRaises(AiHttpError):
                url_guard.validate_outbound_url('http://169.254.169.254/x', allowlist=allow)
        finally:
            icp.set_param('open_ai_connector.outbound_host_allowlist', '')
            self.env['ai.connector']._apply_outbound_policy()

    def test_allowlist_includes_gemini_cloudcode_endpoint(self):
        from odoo.addons.open_ai_connector.tools import http_client
        icp = self.env['ir.config_parameter'].sudo()
        gem = self.env.ref('open_ai_connector.provider_google_gemini_cli')
        self.env['ai.credential'].create({'name': 'G', 'provider_id': gem.id})
        icp.set_param('open_ai_connector.outbound_host_allowlist', 'example.com')
        try:
            self.env['ai.connector']._apply_outbound_policy()
            _bp, allow = http_client._get_policy()
            # the transport-hardcoded Cloud Code host (no base_url field carries it)
            self.assertIn('cloudcode-pa.googleapis.com', allow)
        finally:
            icp.set_param('open_ai_connector.outbound_host_allowlist', '')
            self.env['ai.connector']._apply_outbound_policy()

    def test_allowlist_includes_credential_level_oauth_host(self):
        # A credential's OWN oauth_token_url wins over the provider at runtime
        # (_as_cred_dict), so its host must be in the effective allowlist too —
        # covers custom providers, regional/rotated hosts, and xAI OIDC-discovered
        # endpoints (persisted onto the credential by the wizard).
        from odoo.addons.open_ai_connector.tools import http_client, url_guard
        icp = self.env['ir.config_parameter'].sudo()
        xai = self.env.ref('open_ai_connector.provider_xai_oauth')
        cred = self.env['ai.credential'].create({'name': 'Grok', 'provider_id': xai.id})
        # simulate OIDC discovery persisting a token endpoint on a DIFFERENT host
        cred.sudo().write({'oauth_token_url': 'https://token.example-idp.com/oauth/token'})
        icp.set_param('open_ai_connector.outbound_host_allowlist', 'example.com')
        try:
            self.env['ai.connector']._apply_outbound_policy()
            _bp, allow = http_client._get_policy()
            self.assertIn('token.example-idp.com', allow)
            url_guard.validate_outbound_url(
                'https://token.example-idp.com/oauth/token', allowlist=allow)
        finally:
            icp.set_param('open_ai_connector.outbound_host_allowlist', '')
            self.env['ai.connector']._apply_outbound_policy()

    def test_allowlist_allows_whole_catalog_by_default(self):
        # Every catalog provider's model + auth domain is allowed even with NO
        # credential, so a domain-level allowlist never breaks authentication.
        from odoo.addons.open_ai_connector.tools import http_client
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('open_ai_connector.outbound_host_allowlist', 'example.com')
        try:
            self.env['ai.connector']._apply_outbound_policy()
            _bp, allow = http_client._get_policy()
            self.assertIn('example.com', allow)
            self.assertIn('api.anthropic.com', allow)   # anthropic provider, no cred here
            self.assertIn('chat.qwen.ai', allow)        # qwen device/token host
            self.assertIn('api.minimax.io', allow)      # minimax auth/token host
        finally:
            icp.set_param('open_ai_connector.outbound_host_allowlist', '')
            self.env['ai.connector']._apply_outbound_policy()

    def test_no_allowlist_means_no_restriction(self):
        from odoo.addons.open_ai_connector.tools import http_client
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('open_ai_connector.outbound_host_allowlist', '')
        self.env['ai.connector']._apply_outbound_policy()
        _bp, allow = http_client._get_policy()
        self.assertIsNone(allow)  # empty admin allowlist => unrestricted (no host gate)

    # ── manual paste-back PKCE flow ───────────────────────────────────
    def test_parse_callback_forms(self):
        from odoo.addons.open_ai_connector.tools import oauth
        full = oauth.parse_callback('http://localhost:1455/auth/callback?code=ac_1&state=xyz')
        self.assertEqual(full['code'], 'ac_1')
        self.assertEqual(full['state'], 'xyz')
        self.assertEqual(oauth.parse_callback('?code=ac_2&state=z')['code'], 'ac_2')
        self.assertEqual(oauth.parse_callback('code=ac_3&state=z')['code'], 'ac_3')
        bare = oauth.parse_callback('ac_4')
        self.assertEqual(bare['code'], 'ac_4')
        self.assertIsNone(bare['state'])
        err = oauth.parse_callback('http://x/cb?error=access_denied&error_description=no')
        self.assertEqual(err['error'], 'access_denied')

    def test_authorize_url_includes_extra_params(self):
        from odoo.addons.open_ai_connector.tools import oauth
        cred = {'oauth_auth_url': 'https://auth.openai.com/oauth/authorize',
                'oauth_client_id': 'cid', 'oauth_scopes': 'openid email',
                'oauth_extra_authorize_params': {'codex_cli_simplified_flow': 'true',
                                                 'prompt': 'login'}}
        url, verifier = oauth.external_auth_url(cred, 'http://localhost:1455/auth/callback', 'st8')
        self.assertIn('codex_cli_simplified_flow=true', url)
        self.assertIn('prompt=login', url)
        self.assertIn('code_challenge_method=S256', url)
        self.assertIn('redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback', url)
        self.assertTrue(verifier)

    def test_xai_oauth_has_paste_flow_config(self):
        prov = self.env.ref('open_ai_connector.provider_xai_oauth')
        d = self.env['ai.credential'].create(
            {'name': 'Grok', 'provider_id': prov.id})._as_cred_dict()
        self.assertEqual(d['oauth_redirect_uri'], 'http://127.0.0.1:56121/callback')
        self.assertEqual(d['oauth_extra_authorize_params'].get('plan'), 'generic')

    def test_submit_callback_exchanges_and_connects(self):
        prov = self.env.ref('open_ai_connector.provider_xai_oauth')
        cred = self.env['ai.credential'].create({'name': 'Grok', 'provider_id': prov.id})
        cred.sudo().write({'oauth_state': 'st8', 'oauth_code_verifier': 'v8'})
        wiz = self.env['ai.oauth.wizard'].create({
            'credential_id': cred.id, 'auth_url': 'https://auth.x.ai/oauth2/authorize?x=1',
            'callback_url': 'http://127.0.0.1:56121/callback?code=ac_9&state=st8'})
        with patch('odoo.addons.open_ai_connector.tools.http_client.post_form',
                   return_value={'access_token': 'tok', 'refresh_token': 'r',
                                 'expires_in': 3600}) as mf:
            action = wiz.action_submit_callback()
        self.assertEqual(action['type'], 'ir.actions.act_window_close')
        self.assertEqual(cred.sudo().oauth_access_token, 'tok')
        self.assertEqual(cred.state, 'connected')
        _a, kw = mf.call_args
        self.assertEqual(kw['data']['grant_type'], 'authorization_code')
        self.assertEqual(kw['data']['code'], 'ac_9')
        self.assertEqual(kw['data']['code_verifier'], 'v8')
        self.assertTrue(kw['data']['redirect_uri'].endswith('/callback'))

    def test_submit_callback_state_mismatch_raises(self):
        prov = self.env.ref('open_ai_connector.provider_xai_oauth')
        cred = self.env['ai.credential'].create({'name': 'Grok', 'provider_id': prov.id})
        cred.sudo().write({'oauth_state': 'expected', 'oauth_code_verifier': 'v'})
        wiz = self.env['ai.oauth.wizard'].create({
            'credential_id': cred.id, 'auth_url': 'x',
            'callback_url': 'http://127.0.0.1:56121/callback?code=ac&state=WRONG'})
        with self.assertRaises(UserError):
            wiz.action_submit_callback()

    def test_submit_callback_without_verifier_asks_restart(self):
        # A stale wizard (PKCE verifier already cleared by a prior attempt) must
        # NOT call the token endpoint with code_verifier=null (Anthropic rejects
        # that as "Invalid request format"); it raises a "Restart" UserError.
        prov = self.env.ref('open_ai_connector.provider_claude_oauth')
        cred = self.env['ai.credential'].create({'name': 'Claude', 'provider_id': prov.id})
        cred.sudo().write({'oauth_state': 'st', 'oauth_code_verifier': False})
        wiz = self.env['ai.oauth.wizard'].create({
            'credential_id': cred.id, 'auth_url': 'x',
            'callback_url': 'rawcode#st'})
        with patch('odoo.addons.open_ai_connector.tools.http_client.post_json',
                   side_effect=AssertionError('must not call token endpoint')):
            with self.assertRaises(UserError):
                wiz.action_submit_callback()

    def test_http_client_surfaces_flat_oauth_error(self):
        # OAuth token endpoints return {"error": "...", "error_description": "..."}
        # (a string error, not {"error": {"message": ...}}). _raise_for_status must
        # surface error_description instead of a raw "HTTP 400: {...}" dump.
        from odoo.addons.open_ai_connector.tools import http_client

        class _Resp:
            status_code = 400
            def json(self):
                return {'error': 'invalid_grant',
                        'error_description': "Invalid 'code' in request."}
        with self.assertRaises(http_client.AiHttpError) as cm:
            http_client._raise_for_status(_Resp())
        self.assertEqual(str(cm.exception), "Invalid 'code' in request.")
        self.assertEqual(cm.exception.status_code, 400)

    def test_codex_pkce_start_builds_authorize_url(self):
        # Codex now uses Authorization Code + PKCE: Start must build a codex-shaped
        # authorize URL and attempt the loopback listener on localhost:1455.
        codex = self.env.ref('open_ai_connector.provider_openai_codex')
        cred = self.env['ai.credential'].create({
            'name': 'Codex', 'provider_id': codex.id})
        wiz = self.env['ai.oauth.wizard'].create({'credential_id': cred.id})
        with patch('odoo.addons.open_ai_connector.tools.oauth_loopback.start',
                   return_value=True) as mock_start:
            wiz.action_start()
        self.assertIn('auth.openai.com/oauth/authorize', wiz.auth_url)
        self.assertIn('codex_cli_simplified_flow=true', wiz.auth_url)
        self.assertIn('code_challenge_method=S256', wiz.auth_url)
        self.assertTrue(wiz.listening)
        # the listener was asked to bind the codex loopback redirect
        args = mock_start.call_args[0]
        self.assertEqual(args[1], 'localhost')   # host
        self.assertEqual(args[2], 1455)          # port
        self.assertEqual(args[3], '/auth/callback')
        # PKCE state + verifier were stored on the credential
        self.assertTrue(cred.sudo().oauth_state)
        self.assertTrue(cred.sudo().oauth_code_verifier)

    def test_codex_pkce_loopback_poll_completes(self):
        # With a listener active, a captured redirect completes the flow on poll.
        from odoo.addons.open_ai_connector.tools import oauth_loopback
        codex = self.env.ref('open_ai_connector.provider_openai_codex')
        cred = self.env['ai.credential'].create({'name': 'Codex', 'provider_id': codex.id})
        cred.sudo().write({'oauth_state': 'st_cx', 'oauth_code_verifier': 'v_cx'})
        wiz = self.env['ai.oauth.wizard'].create({
            'credential_id': cred.id, 'auth_url': 'https://auth.openai.com/oauth/authorize?x=1',
            'listening': True})
        with patch.object(oauth_loopback, 'result',
                          return_value={'code': 'ac_cx', 'state': 'st_cx'}), \
             patch.object(oauth_loopback, 'cancel'), \
             patch('odoo.addons.open_ai_connector.tools.http_client.post_form',
                   return_value={'access_token': 'tok', 'refresh_token': 'r',
                                 'expires_in': 3600}) as mf:
            action = wiz.action_poll()
        self.assertEqual(action['type'], 'ir.actions.act_window_close')
        self.assertEqual(cred.sudo().oauth_access_token, 'tok')
        self.assertEqual(cred.state, 'connected')
        self.assertEqual(mf.call_args[1]['data']['grant_type'], 'authorization_code')

    def test_external_poll_pending_reopens(self):
        # No captured redirect yet => poll keeps the wizard open.
        from odoo.addons.open_ai_connector.tools import oauth_loopback
        codex = self.env.ref('open_ai_connector.provider_openai_codex')
        cred = self.env['ai.credential'].create({'name': 'Codex', 'provider_id': codex.id})
        cred.sudo().write({'oauth_state': 'st_cx2'})
        wiz = self.env['ai.oauth.wizard'].create({
            'credential_id': cred.id, 'auth_url': 'x', 'listening': True})
        with patch.object(oauth_loopback, 'result', return_value=None):
            action = wiz.action_poll()
        self.assertEqual(action['res_model'], 'ai.oauth.wizard')
        self.assertFalse(wiz.connected)

    def test_codex_device_poll_pending_then_token(self):
        from odoo.addons.open_ai_connector.tools import oauth
        from odoo.addons.open_ai_connector.tools.http_client import AiHttpError
        codex = self.env.ref('open_ai_connector.provider_openai_codex')
        cred = self.env['ai.credential'].create({
            'name': 'Codex', 'provider_id': codex.id})._as_cred_dict()
        # 403 from the poll endpoint => still pending, no exchange attempted.
        with patch('odoo.addons.open_ai_connector.tools.http_client.post_json',
                   side_effect=AiHttpError(403, 'pending')):
            self.assertEqual(oauth.codex_device_poll(cred, 'deviceauth_abc', 'MP4J'),
                             {'pending': 'authorization_pending'})
        # Poll returns an auth code + verifier, then the form exchange yields tokens.
        with patch('odoo.addons.open_ai_connector.tools.http_client.post_json',
                   return_value={'authorization_code': 'ac_1', 'code_verifier': 'v_1'}), \
             patch('odoo.addons.open_ai_connector.tools.http_client.post_form',
                   return_value={'access_token': 'tok', 'refresh_token': 'ref',
                                 'expires_in': 3600}) as mock_form:
            result = oauth.codex_device_poll(cred, 'deviceauth_abc', 'MP4J')
        self.assertEqual(result['oauth_access_token'], 'tok')
        self.assertEqual(result['oauth_refresh_token'], 'ref')
        # exchange used grant_type=authorization_code with the fixed redirect_uri
        _a, kw = mock_form.call_args
        self.assertEqual(kw['data']['grant_type'], 'authorization_code')
        self.assertTrue(kw['data']['redirect_uri'].endswith('/deviceauth/callback'))

    def test_fetch_models_parses_codex_slug_shape(self):
        # The Codex backend returns {"models":[{"slug":..}]} (not {"data":[{"id"}]}).
        # The fetch must parse slugs and upsert them as ai.model rows.
        codex = self.env.ref('open_ai_connector.provider_openai_codex')
        cred = self.env['ai.credential'].create({
            'name': 'Codex', 'provider_id': codex.id,
            'oauth_access_token': 'tok'})
        payload = {'models': [{'slug': 'gpt-5.5'}, {'slug': 'gpt-5.3-codex'},
                              {'no_slug': 'ignored'}]}
        with patch('odoo.addons.open_ai_connector.tools.http_client.get_json',
                   return_value=payload):
            added, total = codex._fetch_models_with_credential(cred)
        slugs = codex.model_ids.mapped('model_id')
        self.assertIn('gpt-5.5', slugs)
        self.assertIn('gpt-5.3-codex', slugs)
        self.assertEqual((added, total), (2, 2))
        # Re-fetching the same models reports them as available, 0 new — NOT
        # an alarming "0 added".
        with patch('odoo.addons.open_ai_connector.tools.http_client.get_json',
                   return_value=payload):
            added2, total2 = codex._fetch_models_with_credential(cred)
        self.assertEqual((added2, total2), (0, 2))

    def test_fetch_models_falls_back_to_curated_list(self):
        # When the live fetch yields nothing, the curated fallback_models is used
        # so the user still gets a usable model list (Codex offline / API hiccup).
        codex = self.env.ref('open_ai_connector.provider_openai_codex')
        self.assertTrue(codex.get_fallback_models(), "codex should seed fallback models")
        cred = self.env['ai.credential'].create({
            'name': 'Codex', 'provider_id': codex.id, 'oauth_access_token': 'tok'})
        with patch('odoo.addons.open_ai_connector.tools.http_client.get_json',
                   side_effect=Exception('boom')):
            added, total = codex._fetch_models_with_credential(cred)
        self.assertIn('gpt-5.3-codex', codex.model_ids.mapped('model_id'))
        self.assertEqual(total, len(codex.get_fallback_models()))

    def test_claude_oauth_fetch_models_uses_v1_and_bearer(self):
        # The Claude OAuth catalog fetch must hit /v1/models (not /models), use a
        # browser TLS fingerprint (Cloudflare), and authenticate with Bearer +
        # anthropic-beta — NOT x-api-key (which Anthropic rejects for OAuth tokens).
        prov = self.env.ref('open_ai_connector.provider_claude_oauth')
        cred = self.env['ai.credential'].create({
            'name': 'Claude', 'provider_id': prov.id, 'oauth_access_token': 'oauth-tok'})
        cap = {}

        def fake_get_json(url, headers=None, timeout=None, proxy_url=None, impersonate=None):
            cap.update(url=url, headers=headers, impersonate=impersonate)
            return {'data': [{'type': 'model', 'id': 'claude-opus-4-8'},
                             {'type': 'model', 'id': 'claude-fable-5'}]}

        with patch('odoo.addons.open_ai_connector.tools.http_client.get_json',
                   side_effect=fake_get_json):
            added, total = prov._fetch_models_with_credential(cred)
        self.assertTrue(cap['url'].endswith('/v1/models'), cap['url'])
        self.assertEqual(cap['impersonate'], 'chrome')
        self.assertEqual(cap['headers']['Authorization'], 'Bearer oauth-tok')
        self.assertIn('anthropic-beta', cap['headers'])
        self.assertNotIn('x-api-key', cap['headers'])
        self.assertIn('claude-opus-4-8', prov.model_ids.mapped('model_id'))
        self.assertIn('claude-fable-5', prov.model_ids.mapped('model_id'))

    def test_anthropic_apikey_fetch_models_uses_v1_and_xapikey(self):
        # API-key Anthropic still uses x-api-key + anthropic-version against /v1/models.
        prov = self.env.ref('open_ai_connector.provider_anthropic')
        cred = self.env['ai.credential'].create({
            'name': 'Anthropic', 'provider_id': prov.id, 'api_key': 'sk-ant-xxx'})
        cap = {}

        def fake_get_json(url, headers=None, timeout=None, proxy_url=None, impersonate=None):
            cap.update(url=url, headers=headers)
            return {'data': [{'id': 'claude-opus-4-8'}]}

        with patch('odoo.addons.open_ai_connector.tools.http_client.get_json',
                   side_effect=fake_get_json):
            prov._fetch_models_with_credential(cred)
        self.assertTrue(cap['url'].endswith('/v1/models'), cap['url'])
        self.assertEqual(cap['headers']['x-api-key'], 'sk-ant-xxx')
        self.assertNotIn('Authorization', cap['headers'])

    # ── media generation (image / video) ────────────────────────────────
    def test_generate_image_hits_images_endpoint_and_saves_attachment(self):
        import base64
        from datetime import datetime, timedelta
        prov = self.env.ref('open_ai_connector.provider_xai_oauth')
        cred = self.env['ai.credential'].create({
            'name': 'x', 'provider_id': prov.id, 'oauth_access_token': 'tok',
            'oauth_token_expiry': datetime.utcnow() + timedelta(hours=1)})
        png = base64.b64encode(b'\x89PNG-fake').decode()
        cap = {}

        def fake_post_json(url, headers=None, json_body=None, timeout=None,
                           proxy_url=None, max_retries=2, impersonate=None):
            cap.update(url=url, body=json_body, headers=headers)
            return {'data': [{'b64_json': png, 'mime_type': 'image/png'}]}

        with patch('odoo.addons.open_ai_connector.tools.http_client.post_json',
                   side_effect=fake_post_json):
            res = self.env['ai.connector'].generate_image(
                provider='xai-oauth', model='grok-imagine-image',
                prompt='a red apple', credential=cred.id)
        self.assertTrue(cap['url'].endswith('/images/generations'), cap['url'])
        self.assertEqual(cap['body']['model'], 'grok-imagine-image')
        self.assertEqual(cap['body']['prompt'], 'a red apple')
        self.assertEqual(len(res['images']), 1)
        att = self.env['ir.attachment'].browse(res['images'][0]['attachment_id'])
        self.assertTrue(att.exists())
        self.assertEqual(att.mimetype, 'image/png')

    def test_generate_image_force_refreshes_oauth_on_auth_error(self):
        # Stale/invalid OAuth token → 401 → force-refresh → retry succeeds.
        import base64
        from datetime import datetime, timedelta
        prov = self.env.ref('open_ai_connector.provider_xai_oauth')
        cred = self.env['ai.credential'].create({
            'name': 'x', 'provider_id': prov.id, 'oauth_access_token': 'stale',
            'oauth_refresh_token': 'rt',
            'oauth_token_expiry': datetime.utcnow() + timedelta(hours=1)})
        png = base64.b64encode(b'img').decode()
        calls = {'n': 0}

        def fake_post_json(url, headers=None, json_body=None, timeout=None,
                           proxy_url=None, max_retries=2, impersonate=None):
            calls['n'] += 1
            if calls['n'] == 1:
                raise AiHttpError(401, 'The OAuth2 access token could not be validated.')
            return {'data': [{'b64_json': png, 'mime_type': 'image/png'}]}

        def fake_post_form(url, headers=None, data=None, timeout=None, proxy_url=None):
            return {'access_token': 'fresh', 'refresh_token': 'rt2', 'expires_in': 3600}

        with patch('odoo.addons.open_ai_connector.tools.http_client.post_json',
                   side_effect=fake_post_json), \
             patch('odoo.addons.open_ai_connector.tools.http_client.post_form',
                   side_effect=fake_post_form):
            res = self.env['ai.connector'].generate_image(
                provider='xai-oauth', model='grok-imagine-image',
                prompt='apple', credential=cred.id)
        self.assertEqual(calls['n'], 2)                       # failed once, retried
        self.assertEqual(len(res['images']), 1)
        self.assertEqual(cred.sudo().oauth_access_token, 'fresh')  # token refreshed

    def test_generate_video_submits_polls_and_materializes(self):
        from datetime import datetime, timedelta
        prov = self.env.ref('open_ai_connector.provider_xai_oauth')
        cred = self.env['ai.credential'].create({
            'name': 'x', 'provider_id': prov.id, 'oauth_access_token': 'tok',
            'oauth_token_expiry': datetime.utcnow() + timedelta(hours=1)})
        poll_seq = [{'status': 'queued'},
                    {'status': 'done', 'video': {'url': 'https://imgen.x.ai/v.mp4'}}]

        def fake_post_json(url, headers=None, json_body=None, timeout=None,
                           proxy_url=None, max_retries=2, impersonate=None):
            return {'request_id': 'req_1'}

        def fake_get_json(url, headers=None, timeout=None, proxy_url=None, impersonate=None):
            return poll_seq.pop(0)

        def fake_get_bytes(url, headers=None, timeout=None, proxy_url=None, impersonate=None):
            return (b'video-bytes', 'video/mp4')

        with patch('odoo.addons.open_ai_connector.tools.http_client.post_json',
                   side_effect=fake_post_json), \
             patch('odoo.addons.open_ai_connector.tools.http_client.get_json',
                   side_effect=fake_get_json), \
             patch('odoo.addons.open_ai_connector.tools.http_client.get_bytes',
                   side_effect=fake_get_bytes), \
             patch('time.sleep'):
            res = self.env['ai.connector'].generate_video(
                provider='xai-oauth', model='grok-imagine-video', prompt='a cat',
                credential=cred.id, poll_interval=0, poll_timeout=30)
        self.assertEqual(res['status'], 'done')
        self.assertEqual(res['video_url'], 'https://imgen.x.ai/v.mp4')
        self.assertTrue(res['attachment'])
        att = self.env['ir.attachment'].browse(res['attachment']['attachment_id'])
        self.assertEqual(att.mimetype, 'video/mp4')

    def test_generate_image_codex_uses_responses_image_tool(self):
        # OpenAI Codex image gen runs on the ChatGPT OAuth via the /responses
        # image_generation tool (SSE) — NOT /images/generations — and the PNG
        # arrives base64 in an image_generation_call.result item.
        import base64
        from datetime import datetime, timedelta
        prov = self.env.ref('open_ai_connector.provider_openai_codex')
        cred = self.env['ai.credential'].create({
            'name': 'codex', 'provider_id': prov.id, 'oauth_access_token': 'tok',
            'oauth_token_expiry': datetime.utcnow() + timedelta(hours=1)})
        png = base64.b64encode(b'codex-final-png').decode()
        cap = {}

        def fake_post_sse(url, headers=None, json_body=None, timeout=None,
                          proxy_url=None, impersonate=None):
            cap.update(url=url, headers=headers, body=json_body, impersonate=impersonate)
            yield {'type': 'response.image_generation_call.partial_image',
                   'partial_image_b64': base64.b64encode(b'partial').decode()}
            yield {'type': 'response.output_item.done',
                   'item': {'type': 'image_generation_call', 'result': png}}

        with patch('odoo.addons.open_ai_connector.tools.http_client.post_sse',
                   side_effect=fake_post_sse):
            res = self.env['ai.connector'].generate_image(
                provider='openai-codex', model='gpt-image-2-high',
                prompt='a blue car', credential=cred.id)
        self.assertTrue(cap['url'].endswith('/responses'), cap['url'])
        self.assertEqual(cap['impersonate'], 'chrome')          # uTLS for Codex Cloudflare
        self.assertEqual(cap['headers'].get('originator'), 'codex_cli_rs')
        self.assertEqual(cap['body']['model'], 'gpt-5.5')        # host model invokes the tool
        tool = cap['body']['tools'][0]
        self.assertEqual(tool['type'], 'image_generation')
        self.assertEqual(tool['model'], 'gpt-image-2')
        self.assertEqual(tool['quality'], 'high')                # from the -high tier id
        self.assertTrue(cap['body']['stream'])
        self.assertEqual(len(res['images']), 1)
        self.assertEqual(res['images'][0]['b64'], png)           # final result, not the partial
        att = self.env['ir.attachment'].browse(res['images'][0]['attachment_id'])
        self.assertEqual(att.mimetype, 'image/png')

    def test_provider_media_capability_flags(self):
        # xAI does image+video; Codex image is enabled (plan-gated: works on
        # Team/Pro/paid plans, 400s with a clear message on Free/Plus).
        codex = self.env.ref('open_ai_connector.provider_openai_codex')
        self.assertTrue(codex.supports_image_gen)
        self.assertFalse(codex.supports_video_gen)
        self.assertEqual(codex.default_image_model, 'gpt-image-2-medium')
        xai = self.env.ref('open_ai_connector.provider_xai')
        self.assertTrue(xai.supports_image_gen and xai.supports_video_gen)
        self.assertEqual(xai.default_video_model, 'grok-imagine-video')
        xo = self.env.ref('open_ai_connector.provider_xai_oauth')
        self.assertTrue(xo.supports_image_gen and xo.supports_video_gen)

    def test_post_sse_decodes_byte_lines(self):
        # SSE responses with no charset yield bytes from iter_lines; post_sse
        # must decode them, not crash on line.startswith('data:') (the Codex
        # backend's text/event-stream omits charset).
        from unittest.mock import MagicMock
        from odoo.addons.open_ai_connector.tools import http_client
        fake = MagicMock()
        fake.status_code = 200
        fake.encoding = None
        fake.iter_lines.return_value = iter([b'data: {"x": 1}', b'', b'data: [DONE]'])
        with patch.object(http_client.requests, 'post', return_value=fake):
            events = list(http_client.post_sse('http://x', json_body={}))
        self.assertEqual(events, [{'x': 1}])

    def test_reload_notification_uses_soft_reload_tag(self):
        # soft_reload is a client-action TAG, not a type — the wrong shape made
        # Fetch Models / Test Connection raise 'ActionManager can't handle
        # ir.actions.soft_reload'.
        act = self.env['ai.credential']._reload_notification_static('done')
        nxt = act['params']['next']
        self.assertEqual(nxt['type'], 'ir.actions.client')
        self.assertEqual(nxt['tag'], 'soft_reload')

    # ── Claude.ai OAuth + xAI OIDC discovery + loopback server ──
    def test_claude_oauth_provider_seeded(self):
        prov = self.env.ref('open_ai_connector.provider_claude_oauth')
        self.assertEqual(prov.api_mode, 'anthropic_messages')
        self.assertEqual(prov.auth_type, 'oauth_external')
        self.assertTrue(prov.is_wired)
        d = self.env['ai.credential'].create(
            {'name': 'Claude', 'provider_id': prov.id})._as_cred_dict()
        self.assertEqual(d['oauth_flavor'], 'anthropic')
        self.assertEqual(d['oauth_auth_url'], 'https://claude.ai/oauth/authorize')
        self.assertEqual(d['oauth_redirect_uri'], 'http://localhost:54545/callback')

    def test_claude_oauth_inference_headers(self):
        # An OAuth (claude.ai) token authenticates Messages via Bearer +
        # anthropic-beta, NOT x-api-key (which is for API-key Anthropic).
        from odoo.addons.open_ai_connector.tools import auth
        prov = {'auth_type': 'oauth_external', 'api_mode': 'anthropic_messages',
                'oauth_flavor': 'anthropic', 'base_url': 'https://api.anthropic.com'}
        cred = {'oauth_access_token': 'oauth-tok'}
        r = auth.resolve(prov, cred)
        self.assertEqual(r['headers']['Authorization'], 'Bearer oauth-tok')
        self.assertIn('oauth-2025-04-20', r['headers']['anthropic-beta'])
        self.assertNotIn('x-api-key', r['headers'])
        # API-key Anthropic still uses x-api-key
        r2 = auth.resolve({'auth_type': 'api_key', 'api_mode': 'anthropic_messages'},
                          {'api_key': 'sk-ant'})
        self.assertEqual(r2['headers']['x-api-key'], 'sk-ant')
        self.assertNotIn('Authorization', r2['headers'])

    def test_claude_oauth_token_exchange_uses_json(self):
        # Anthropic's token endpoint speaks JSON, not form-urlencoded.
        from odoo.addons.open_ai_connector.tools import oauth
        cred = {'oauth_token_url': 'https://api.anthropic.com/v1/oauth/token',
                'oauth_client_id': 'cid', 'oauth_flavor': 'anthropic'}
        with patch('odoo.addons.open_ai_connector.tools.http_client.post_json',
                   return_value={'access_token': 't', 'refresh_token': 'r',
                                 'expires_in': 3600}) as mj, \
             patch('odoo.addons.open_ai_connector.tools.http_client.post_form',
                   side_effect=AssertionError('anthropic must use JSON')):
            out = oauth.exchange_code(cred, 'code1', 'verifier1',
                                      'http://localhost:54545/callback', state='st1')
        self.assertEqual(out['oauth_access_token'], 't')
        body = mj.call_args[1]['json_body']
        self.assertEqual(body['grant_type'], 'authorization_code')
        self.assertEqual(body['code_verifier'], 'verifier1')
        # Anthropic REQUIRES `state` echoed in the token body (else it rejects
        # the exchange as "Invalid request format").
        self.assertEqual(body['state'], 'st1')
        # token exchange is sent with a browser TLS fingerprint (Cloudflare)
        self.assertEqual(mj.call_args[1].get('impersonate'), 'chrome')

    def test_claude_oauth_token_exchange_splits_code_hash_state(self):
        # claude.ai (code=true / manual paste) returns the code as "<code>#<state>".
        # The embedded state must be split out and echoed; the embedded value
        # wins over a caller-supplied state.
        from odoo.addons.open_ai_connector.tools import oauth
        cred = {'oauth_token_url': 'https://api.anthropic.com/v1/oauth/token',
                'oauth_client_id': 'cid', 'oauth_flavor': 'anthropic'}
        with patch('odoo.addons.open_ai_connector.tools.http_client.post_json',
                   return_value={'access_token': 't'}) as mj:
            oauth.exchange_code(cred, 'rawcode#embedded', 'v1',
                                'http://localhost:54545/callback', state='fallback')
        body = mj.call_args[1]['json_body']
        self.assertEqual(body['code'], 'rawcode')
        self.assertEqual(body['state'], 'embedded')
        # Non-anthropic providers: code is sent verbatim, no state field injected.
        from odoo.addons.open_ai_connector.tools import oauth as oauth2
        with patch('odoo.addons.open_ai_connector.tools.http_client.post_form',
                   return_value={'access_token': 't'}) as mf:
            oauth2.exchange_code({'oauth_token_url': 'https://auth.openai.com/oauth/token',
                                  'oauth_client_id': 'c'}, 'abc#notstate', 'v',
                                 'http://localhost:1455/auth/callback', state='x')
        self.assertEqual(mf.call_args[1]['data']['code'], 'abc#notstate')
        self.assertNotIn('state', mf.call_args[1]['data'])

    # ── Claude Code signature (headers + system prompt + TLS) ──
    def test_claude_oauth_signature_headers(self):
        from odoo.addons.open_ai_connector.tools import auth
        r = auth.resolve(
            {'auth_type': 'oauth_external', 'api_mode': 'anthropic_messages',
             'oauth_flavor': 'anthropic', 'base_url': 'https://api.anthropic.com'},
            {'oauth_access_token': 'tok'})
        h = r['headers']
        self.assertEqual(h['User-Agent'], 'claude-cli/2.1.63 (external, cli)')
        self.assertEqual(h['X-App'], 'cli')
        self.assertEqual(h['X-Stainless-Runtime'], 'node')
        self.assertIn('claude-code-20250219', h['anthropic-beta'])
        self.assertIn('oauth-2025-04-20', h['anthropic-beta'])
        self.assertNotIn('x-api-key', h)

    def test_claude_oauth_system_prompt_injection(self):
        from odoo.addons.open_ai_connector.tools import anthropic as ant
        from odoo.addons.open_ai_connector.tools.transport_base import RequestContext
        t = ant.AnthropicTransport()
        oauth_ctx = RequestContext(
            model='claude-x',
            messages=[{'role': 'system', 'content': 'be terse'},
                      {'role': 'user', 'content': 'hi'}],
            provider={'auth_type': 'oauth_external', 'api_mode': 'anthropic_messages',
                      'oauth_flavor': 'anthropic'},
            headers={'Authorization': 'Bearer tok'})
        body = t.build_body(oauth_ctx)
        self.assertEqual(body['system'][0]['text'], ant.CLAUDE_CODE_IDENTITY)
        self.assertEqual(body['system'][1]['text'], 'be terse')
        # api-key mode: NO injection, system stays a plain string
        api_ctx = RequestContext(
            model='claude-x',
            messages=[{'role': 'system', 'content': 'be terse'},
                      {'role': 'user', 'content': 'hi'}],
            provider={'auth_type': 'api_key', 'api_mode': 'anthropic_messages'}, headers={})
        self.assertEqual(t.build_body(api_ctx)['system'], 'be terse')

    def test_claude_oauth_chat_impersonates_and_signs(self):
        from datetime import datetime, timedelta
        prov = self.env.ref('open_ai_connector.provider_claude_oauth')
        cred = self.env['ai.credential'].create({
            'name': 'Claude', 'provider_id': prov.id, 'oauth_access_token': 'oauth-tok',
            'oauth_token_expiry': datetime.utcnow() + timedelta(hours=1), 'is_default': True})
        cap = {}

        def fake_post_json(url, headers=None, json_body=None, timeout=None,
                           proxy_url=None, max_retries=2, impersonate=None):
            cap.update(url=url, headers=headers, body=json_body, impersonate=impersonate)
            return {'content': [{'type': 'text', 'text': 'hi'}], 'stop_reason': 'end_turn',
                    'usage': {'input_tokens': 1, 'output_tokens': 1}}

        with patch('odoo.addons.open_ai_connector.tools.http_client.post_json',
                   side_effect=fake_post_json):
            res = self.env['ai.connector'].chat(
                provider='claude-oauth', model='claude-sonnet-4-5-20250929',
                messages=[{'role': 'user', 'content': 'hi'}], credential=cred.id)
        self.assertEqual(res['content'], 'hi')
        self.assertEqual(cap['impersonate'], 'chrome')                 # uTLS path
        self.assertEqual(cap['headers']['User-Agent'], 'claude-cli/2.1.63 (external, cli)')
        self.assertIn('claude-code-20250219', cap['headers']['anthropic-beta'])
        self.assertTrue(cap['headers'].get('x-client-request-id'))      # per-request id
        self.assertTrue(cap['headers'].get('X-Claude-Code-Session-Id'))  # stable session id
        self.assertEqual(cap['body']['system'][0]['text'],
                         "You are Claude Code, Anthropic's official CLI for Claude.")

    def test_minimax_oauth_does_not_get_claude_code_signature(self):
        # MiniMax is anthropic_messages + OAuth but NOT Claude — it must NOT get
        # the claude-cli UA / claude-code beta / "You are Claude Code" prefix.
        from odoo.addons.open_ai_connector.tools import auth, anthropic as ant
        from odoo.addons.open_ai_connector.tools.transport_base import RequestContext
        prov = {'auth_type': 'oauth_device_code', 'api_mode': 'anthropic_messages',
                'oauth_flavor': 'minimax', 'base_url': 'https://api.minimax.io/anthropic'}
        h = auth.resolve(prov, {'oauth_access_token': 'mtok'})['headers']
        self.assertEqual(h['Authorization'], 'Bearer mtok')   # OAuth bearer
        self.assertNotIn('x-api-key', h)
        self.assertNotIn('User-Agent', h)                      # no claude-cli UA
        self.assertNotIn('anthropic-beta', h)                  # no claude-code betas
        t = ant.AnthropicTransport()
        ctx = RequestContext(model='MiniMax-M2',
                             messages=[{'role': 'system', 'content': 'hi'},
                                       {'role': 'user', 'content': 'yo'}],
                             provider=prov, headers={'Authorization': 'Bearer mtok'})
        self.assertFalse(t._oauth_mode(ctx))                   # not Claude Code mode
        self.assertIsNone(t._impersonate(ctx))                 # no uTLS
        self.assertEqual(t.build_body(ctx)['system'], 'hi')    # no identity injection

    # ── MiniMax user-code flow ────────────────────────────────────────────
    def test_minimax_provider_is_user_code_flow(self):
        prov = self.env.ref('open_ai_connector.provider_minimax_oauth')
        self.assertEqual(prov.auth_type, 'oauth_device_code')
        self.assertEqual(prov.oauth_flavor, 'minimax')

    def test_minimax_start_and_poll(self):
        from odoo.addons.open_ai_connector.tools import oauth
        cred = {'oauth_auth_url': 'https://api.minimax.io/oauth/code',
                'oauth_token_url': 'https://api.minimax.io/oauth/token',
                'oauth_client_id': 'cid', 'oauth_scopes': 'group_id'}
        with patch('odoo.addons.open_ai_connector.tools.http_client.post_form',
                   return_value={'user_code': 'UC1', 'verification_uri': 'https://mm/verify',
                                 'expired_in': 600, 'interval': 2000}) as mf:
            start = oauth.minimax_start(cred)
        self.assertEqual(start['user_code'], 'UC1')
        self.assertTrue(start['code_verifier'])
        self.assertEqual(mf.call_args[1]['data']['code_challenge_method'], 'S256')
        # poll: pending, then success
        with patch('odoo.addons.open_ai_connector.tools.http_client.post_form',
                   return_value={'status': 'pending'}):
            self.assertEqual(oauth.minimax_poll(cred, 'UC1', 'v'), {'pending': 'pending'})
        with patch('odoo.addons.open_ai_connector.tools.http_client.post_form',
                   return_value={'status': 'success', 'access_token': 'at',
                                 'refresh_token': 'rt', 'expired_in': 3600}):
            out = oauth.minimax_poll(cred, 'UC1', 'v')
        self.assertEqual(out['oauth_access_token'], 'at')
        self.assertEqual(out['oauth_refresh_token'], 'rt')

    # ── Qwen device flow ──────────────────────────────────────────────────
    def test_qwen_provider_is_device_flow(self):
        prov = self.env.ref('open_ai_connector.provider_qwen_oauth')
        self.assertEqual(prov.auth_type, 'oauth_device_code')
        self.assertEqual(prov.oauth_flavor, 'qwen')
        d = self.env['ai.credential'].create(
            {'name': 'Qwen', 'provider_id': prov.id})._as_cred_dict()
        self.assertEqual(d['oauth_device_authorization_url'],
                         'https://chat.qwen.ai/api/v1/oauth2/device/code')

    def test_qwen_device_start_and_poll(self):
        from odoo.addons.open_ai_connector.tools import oauth
        from odoo.addons.open_ai_connector.tools.http_client import AiHttpError
        cred = {'oauth_device_authorization_url': 'https://chat.qwen.ai/api/v1/oauth2/device/code',
                'oauth_token_url': 'https://chat.qwen.ai/api/v1/oauth2/token',
                'oauth_client_id': 'cid', 'oauth_scopes': 'openid'}
        with patch('odoo.addons.open_ai_connector.tools.http_client.post_form',
                   return_value={'device_code': 'DC1', 'user_code': 'UC',
                                 'verification_uri_complete': 'https://qwen/v?x', 'interval': 5}):
            start = oauth.qwen_device_start(cred)
        self.assertEqual(start['device_code'], 'DC1')
        self.assertEqual(start['verification_uri'], 'https://qwen/v?x')
        self.assertTrue(start['code_verifier'])
        # pending (authorization_pending) then success with resource_url -> base
        with patch('odoo.addons.open_ai_connector.tools.http_client.post_form',
                   side_effect=AiHttpError(400, 'pending', body={'error': 'authorization_pending'})):
            self.assertEqual(oauth.qwen_device_poll(cred, 'DC1', 'v'),
                             {'pending': 'authorization_pending'})
        with patch('odoo.addons.open_ai_connector.tools.http_client.post_form',
                   return_value={'access_token': 'at', 'refresh_token': 'rt',
                                 'expires_in': 3600, 'resource_url': 'portal.qwen.ai'}):
            out = oauth.qwen_device_poll(cred, 'DC1', 'v')
        self.assertEqual(out['oauth_access_token'], 'at')
        self.assertEqual(out['qwen_base_url'], 'https://portal.qwen.ai/v1')

    def test_oidc_discovery_parses_endpoints(self):
        from odoo.addons.open_ai_connector.tools import oauth
        doc = {'authorization_endpoint': 'https://auth.x.ai/o/authorize',
               'token_endpoint': 'https://auth.x.ai/o/token', 'issuer': 'https://auth.x.ai'}
        with patch('odoo.addons.open_ai_connector.tools.http_client.get_json',
                   return_value=doc):
            out = oauth.discover_oidc('https://auth.x.ai/.well-known/openid-configuration')
        self.assertEqual(out['oauth_auth_url'], 'https://auth.x.ai/o/authorize')
        self.assertEqual(out['oauth_token_url'], 'https://auth.x.ai/o/token')

    def test_xai_oauth_has_discovery_url(self):
        prov = self.env.ref('open_ai_connector.provider_xai_oauth')
        self.assertEqual(prov.oauth_discovery_url,
                         'https://auth.x.ai/.well-known/openid-configuration')

    def test_loopback_server_captures_code(self):
        # Bind an ephemeral loopback port, hit the callback path, read the code.
        import socket as _socket
        import urllib.request
        from odoo.addons.open_ai_connector.tools import oauth_loopback
        s = _socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
        state = 'st_lb'
        self.assertTrue(oauth_loopback.start(state, '127.0.0.1', port, '/cb', timeout=10))
        try:
            urllib.request.urlopen(
                'http://127.0.0.1:%d/cb?code=AC9&state=st_lb' % port, timeout=5).read()
            # the listener thread stores asynchronously; poll briefly
            got = None
            for _ in range(50):
                got = oauth_loopback.result(state)
                if got:
                    break
                __import__('time').sleep(0.05)
            self.assertIsNotNone(got)
            self.assertEqual(got['code'], 'AC9')
            self.assertEqual(got['state'], 'st_lb')
        finally:
            oauth_loopback.cancel(state)

    def test_streaming_emulated(self):
        # base Transport.stream falls back to complete() when not overridden;
        # chat_completions overrides it with a real SSE path, so patch post_sse.
        sse_events = [
            {'choices': [{'delta': {'content': 'Hel'}}]},
            {'choices': [{'delta': {'content': 'lo'}, 'finish_reason': 'stop'}]},
            {'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}},
        ]
        with patch('odoo.addons.open_ai_connector.tools.http_client.post_sse',
                   return_value=iter(sse_events)):
            chunks = list(self.env['ai.connector'].chat(
                provider='openrouter', model='openai/gpt-5',
                messages=[{'role': 'user', 'content': 'hi'}], stream=True))
        deltas = ''.join(c['delta'] for c in chunks if c.get('delta'))
        self.assertEqual(deltas, 'Hello')
        self.assertTrue(chunks[-1]['done'])
        self.assertEqual(chunks[-1]['content'], 'Hello')
