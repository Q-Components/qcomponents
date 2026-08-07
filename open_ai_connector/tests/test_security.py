# -*- coding: utf-8 -*-
"""Security regression tests.

Covers the hardening added in 19.0.1.11.0: the SSRF outbound-URL guard,
credential authorization in chat() (no borrowing keys you can't access),
secret-field hiding from non-managers, and per-user completion-log isolation.
"""
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import AccessError, UserError

from odoo.addons.open_ai_connector.tools import url_guard
from odoo.addons.open_ai_connector.tools.http_client import AiHttpError


@tagged('post_install', '-at_install')
class TestSecurity(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.codex = cls.env.ref('open_ai_connector.provider_openai_codex')
        cls.anthropic = cls.env.ref('open_ai_connector.provider_anthropic')
        cls.g_user = cls.env.ref('open_ai_connector.group_ai_user')
        cls.g_mgr = cls.env.ref('open_ai_connector.group_ai_manager')
        cls.g_internal = cls.env.ref('base.group_user')

    def _make_user(self, login, groups):
        return self.env['res.users'].create({
            'name': login, 'login': login,
            'company_id': self.env.company.id,
            'company_ids': [(6, 0, [self.env.company.id])],
            'group_ids': [(6, 0, [g.id for g in groups])],  # v19: group_ids, not groups_id
        })

    # ── SSRF guard ────────────────────────────────────────────────────
    def test_ssrf_blocks_metadata_linklocal_and_schemes(self):
        for bad in ('http://169.254.169.254/latest/meta-data/',
                    'http://metadata.google.internal/computeMetadata/v1/',
                    'https://[fe80::1]/x',
                    'https://[::ffff:169.254.169.254]/x',  # IPv4-mapped bypass
                    'https://рр.example/x',       # non-ASCII / IDN
                    'file:///etc/passwd',
                    'gopher://10.0.0.1/'):
            with self.assertRaises(AiHttpError):
                url_guard.validate_outbound_url(bad)

    def test_ssrf_allows_public_and_localhost(self):
        # Public literal IP and loopback (self-hosted Ollama/vLLM) must pass.
        url_guard.validate_outbound_url('https://1.1.1.1/v1/chat/completions')
        url_guard.validate_outbound_url('http://127.0.0.1:11434/v1')

    def test_ssrf_block_private_optin(self):
        with self.assertRaises(AiHttpError):
            url_guard.validate_outbound_url('http://127.0.0.1:11434/v1', block_private=True)

    def test_ssrf_allowlist(self):
        # subdomain logic (offline)
        self.assertTrue(url_guard._host_allowed('api.openai.com', ['openai.com']))
        self.assertFalse(url_guard._host_allowed('evil.com', ['openai.com']))
        # allowed host passes; off-list host is refused before any DNS
        url_guard.validate_outbound_url('https://1.1.1.1/v1', allowlist=['1.1.1.1'])
        with self.assertRaises(AiHttpError):
            url_guard.validate_outbound_url('https://1.1.1.1/v1', allowlist=['openai.com'])

    def test_safe_resolve_pins_and_blocks(self):
        # literal IP: nothing to pin
        self.assertIsNone(url_guard.safe_resolve('1.2.3.4', 443, block_private=False))
        # localhost resolves locally (offline); allowed unless block_private
        ip = url_guard.safe_resolve('localhost', 80, block_private=False)
        self.assertTrue(ip)  # a loopback IP to pin
        with self.assertRaises(AiHttpError):
            url_guard.safe_resolve('localhost', 80, block_private=True)

    def test_proxy_validation(self):
        # scheme allowlist + internal/metadata rejection; returns (host, port)
        self.assertEqual(url_guard.validate_proxy_url('http://proxy.example:3128')[0],
                         'proxy.example')
        with self.assertRaises(AiHttpError):
            url_guard.validate_proxy_url('ftp://proxy.example:21')
        with self.assertRaises(AiHttpError):
            url_guard.validate_proxy_url('http://169.254.169.254:8080')
        # schemeless value must still be parsed and vetted (fail closed)
        with self.assertRaises(AiHttpError):
            url_guard.validate_proxy_url('169.254.169.254:8080')
        # loopback proxy refused only under lockdown
        with self.assertRaises(AiHttpError):
            url_guard.validate_proxy_url('http://127.0.0.1:8080', block_private=True)

    def test_ssrf_get_bytes_blocks_redirect_to_internal(self):
        """get_bytes follows redirects MANUALLY and re-vets each hop, so a 302 to
        a cloud-metadata / internal address is blocked (allow_redirects=True would
        have followed it straight past the guard)."""
        from unittest.mock import patch
        from odoo.addons.open_ai_connector.tools import http_client

        class _Resp:
            def __init__(self, status, headers=None, content=b''):
                self.status_code, self.headers, self.content = status, headers or {}, content
            def close(self):
                pass

        seen = []

        def fake_get(url, **kw):
            seen.append(url)
            # first (public, literal-IP) hop redirects to the metadata service
            return _Resp(302, {'Location': 'http://169.254.169.254/latest/meta-data/'})

        with patch.object(http_client, 'requests') as rq:
            rq.get.side_effect = fake_get
            with self.assertRaises(AiHttpError):
                http_client.get_bytes('https://1.1.1.1/img.png')
        # the metadata hop was rejected BEFORE any request was issued to it
        self.assertEqual(seen, ['https://1.1.1.1/img.png'])

    def test_get_bytes_follows_public_redirect_and_drops_auth(self):
        """Legit cross-origin redirect to another public host is followed, the
        body is returned, and the Authorization header is NOT leaked to the new
        origin."""
        from unittest.mock import patch
        from odoo.addons.open_ai_connector.tools import http_client

        class _Resp:
            def __init__(self, status, headers=None, content=b''):
                self.status_code, self.headers, self.content = status, headers or {}, content
            def close(self):
                pass

        seen = []

        def fake_get(url, **kw):
            seen.append((url, dict(kw.get('headers') or {})))
            if url == 'https://1.1.1.1/img.png':
                return _Resp(302, {'Location': 'https://8.8.8.8/cdn/img.png'})
            return _Resp(200, {'Content-Type': 'image/png'}, content=b'PNGDATA')

        with patch.object(http_client, 'requests') as rq:
            rq.get.side_effect = fake_get
            content, ctype = http_client.get_bytes(
                'https://1.1.1.1/img.png', headers={'Authorization': 'Bearer secret'})
        self.assertEqual(content, b'PNGDATA')
        self.assertEqual(ctype, 'image/png')
        self.assertEqual(len(seen), 2)
        self.assertIn('Authorization', seen[0][1])          # sent to the original host
        self.assertNotIn('Authorization', seen[1][1])       # stripped on cross-origin hop

    def test_dns_pin_redirects_then_clears(self):
        import socket
        from odoo.addons.open_ai_connector.tools import dns_pin
        dns_pin.set_pin('pinned.invalid', '127.0.0.1')
        try:
            ips = {i[4][0] for i in socket.getaddrinfo('pinned.invalid', 80)}
            self.assertIn('127.0.0.1', ips)
        finally:
            dns_pin.clear_pins()
        # after clearing, the bogus host no longer resolves to the pin
        with self.assertRaises(OSError):
            socket.getaddrinfo('pinned.invalid', 80)

    def test_outbound_policy_loaded_from_config(self):
        from odoo.addons.open_ai_connector.tools import http_client
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('open_ai_connector.block_private_endpoints', 'True')
        icp.set_param('open_ai_connector.outbound_host_allowlist', 'api.openai.com, openrouter.ai')
        try:
            self.env['ai.connector']._apply_outbound_policy()
            block_private, allowlist = http_client._get_policy()
            self.assertTrue(block_private)
            # The admin's hosts are present; the effective list also unions the
            # whole provider catalog's model/auth domains so auth never breaks.
            self.assertIn('api.openai.com', allowlist)
            self.assertIn('openrouter.ai', allowlist)
            self.assertIn('api.anthropic.com', allowlist)  # catalog provider, auto-allowed
        finally:
            # reset config + thread-local so other tests see safe defaults
            icp.set_param('open_ai_connector.block_private_endpoints', 'False')
            icp.set_param('open_ai_connector.outbound_host_allowlist', '')
            self.env['ai.connector']._apply_outbound_policy()
        self.assertEqual(http_client._get_policy(), (False, None))

    # ── credential authorization (chat credential-borrowing) ───────────
    def test_chat_rejects_unauthorized_credential(self):
        company_b = self.env['res.company'].create({'name': 'AI Sec Co B'})
        cred_b = self.env['ai.credential'].create({
            'name': 'B key', 'provider_id': self.codex.id,
            'company_id': company_b.id, 'api_key': 'sk-b'})
        ai_user = self._make_user('ai_sec_user', [self.g_internal, self.g_user])
        # ai_user is in company A only; cred_b lives in company B -> the
        # multi-company record rule denies read -> chat() must refuse.
        with self.assertRaises(AccessError):
            self.env['ai.connector'].with_user(ai_user).chat(
                provider=self.codex, model='gpt-5.5',
                messages=[{'role': 'user', 'content': 'hi'}],
                credential=cred_b.id)

    def test_chat_rejects_credential_provider_mismatch(self):
        cred = self.env['ai.credential'].create({
            'name': 'codex key', 'provider_id': self.codex.id, 'api_key': 'sk-x'})
        with self.assertRaises(UserError):
            self.env['ai.connector'].chat(
                provider=self.anthropic, model='claude',
                messages=[{'role': 'user', 'content': 'hi'}],
                credential=cred.id)

    def test_non_ai_user_cannot_chat(self):
        plain = self._make_user('plain_sec', [self.g_internal])
        with self.assertRaises(AccessError):
            self.env['ai.connector'].with_user(plain).chat(
                provider=self.codex, model='gpt-5.5',
                messages=[{'role': 'user', 'content': 'hi'}])

    # ── secret field protection ────────────────────────────────────────
    def test_secret_fields_hidden_from_ai_user(self):
        ai_user = self._make_user('ai_sec_u2', [self.g_internal, self.g_user])
        prov_fields = self.env['ai.provider'].with_user(ai_user).fields_get()
        self.assertNotIn('oauth_client_secret', prov_fields,
                         "provider OAuth client secret must be manager-only")
        cred_fields = self.env['ai.credential'].with_user(ai_user).fields_get()
        for secret in ('api_key', 'oauth_access_token', 'oauth_refresh_token',
                       'oauth_client_secret', 'aws_secret_access_key',
                       'oauth_state', 'oauth_code_verifier', 'oauth_flow_uid',
                       'gemini_project_id',
                       'oauth_auth_url', 'oauth_token_url', 'oauth_device_authorization_url',
                       'base_url', 'proxy_url', 'extra_headers'):
            self.assertNotIn(secret, cred_fields,
                             "credential routing/secret %s leaked to AI User" % secret)

    # ── completion-log isolation ───────────────────────────────────────
    def test_completion_log_user_sees_only_own(self):
        u1 = self._make_user('log_u1', [self.g_internal, self.g_user])
        u2 = self._make_user('log_u2', [self.g_internal, self.g_user])
        mgr = self._make_user('log_mgr', [self.g_internal, self.g_mgr])
        Log = self.env['ai.completion.log'].sudo()
        log1 = Log.create({'model': 'm1', 'user_id': u1.id, 'company_id': self.env.company.id})
        log2 = Log.create({'model': 'm2', 'user_id': u2.id, 'company_id': self.env.company.id})
        both = log1 | log2
        seen_u1 = self.env['ai.completion.log'].with_user(u1).search([('id', 'in', both.ids)])
        self.assertEqual(seen_u1, log1, "AI User must only see their own logs")
        seen_mgr = self.env['ai.completion.log'].with_user(mgr).search([('id', 'in', both.ids)])
        self.assertEqual(seen_mgr, both, "AI Manager must see all logs")
