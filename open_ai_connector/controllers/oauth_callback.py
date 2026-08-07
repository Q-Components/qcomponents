# -*- coding: utf-8 -*-
"""OAuth authorization-code (PKCE) redirect handler.

The OAuth wizard sends the user to the provider's authorization URL with
``redirect_uri=<base>/ai/oauth/callback`` and a random ``state``. The provider
redirects back here with ``code`` + ``state``; we look up the credential by
state, exchange the code for tokens (PKCE) and store them.
"""
import hmac
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class AiOAuthCallback(http.Controller):

    @http.route('/ai/oauth/callback', type='http', auth='user', methods=['GET'], csrf=False)
    def callback(self, code=None, state=None, error=None, **kwargs):
        # Completing an OAuth flow writes provider tokens onto a credential — a
        # manager-only operation. auth='user' only proves *some* login; gate on
        # the manager group and bind the flow to the user who started it so a
        # different logged-in user can't replay a code/state to inject their own
        # tokens into someone else's credential.
        if not request.env.user.has_group('open_ai_connector.group_ai_manager'):
            return request.make_response("Not authorized.")

        # Find the pending flow THIS user initiated, matching state in
        # constant time (no SQL-equality timing oracle).
        cred = None
        if state:
            Cred = request.env['ai.credential'].sudo()
            candidates = Cred.search([('oauth_flow_uid', '=', request.env.uid),
                                      ('oauth_state', '!=', False)])
            cred = next((c for c in candidates
                         if hmac.compare_digest(c.oauth_state or '', state or '')), None)

        def _clear(c):
            if c:
                c.write({'oauth_state': False, 'oauth_code_verifier': False,
                         'oauth_flow_uid': False})

        if error:
            _logger.warning("OAuth callback returned error=%s", error)
            _clear(cred)
            return request.make_response(
                "OAuth authorization failed. Return to Odoo and restart the setup.")
        if not code or not state:
            _clear(cred)
            return request.make_response("Missing code/state.")
        if not cred:
            return request.make_response("Unknown or expired OAuth state — restart the setup.")

        # Load the configurable SSRF policy before the token-exchange POST
        # (this public path is otherwise easy to forget — see security review).
        request.env['ai.connector'].sudo()._apply_outbound_policy()
        from ..tools import oauth
        redirect_uri = (request.env['ir.config_parameter'].sudo()
                        .get_param('web.base.url') or '').rstrip('/') + '/ai/oauth/callback'
        try:
            tokens = oauth.exchange_code(
                cred._as_cred_dict(), code, cred.oauth_code_verifier, redirect_uri)
        except Exception:  # noqa: BLE001
            _logger.exception("OAuth code exchange failed for credential %s", cred.id)
            # Invalidate the one-time state/verifier so a failed code can't be retried.
            cred.write({'oauth_state': False, 'oauth_code_verifier': False,
                        'oauth_flow_uid': False})
            return request.make_response(
                "Token exchange failed. Check the server logs and restart the setup.")
        cred._apply_token_updates(tokens)
        cred.write({'state': 'connected', 'oauth_state': False,
                    'oauth_code_verifier': False, 'oauth_flow_uid': False})
        return request.make_response(
            "AI provider connected successfully. You can close this tab and return to Odoo.")
