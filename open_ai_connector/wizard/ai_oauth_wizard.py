# -*- coding: utf-8 -*-
"""ai.oauth.wizard — drive the device-code / PKCE OAuth flows for a credential."""
import hmac
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AiOauthWizard(models.TransientModel):
    _name = 'ai.oauth.wizard'
    _description = 'AI OAuth Setup'

    credential_id = fields.Many2one('ai.credential', string='Credential', required=True)
    auth_type = fields.Selection(related='credential_id.auth_type')

    # Device-code flow
    device_code = fields.Char(readonly=True)
    user_code = fields.Char(string='User Code', readonly=True)
    verification_uri = fields.Char(string='Verification URL', readonly=True)
    device_status = fields.Char(readonly=True)
    connected = fields.Boolean(readonly=True,
                               help="Set once tokens are stored; stops the auto-poll widget.")

    # External / PKCE flow
    auth_url = fields.Char(string='Authorization URL', readonly=True)
    callback_url = fields.Char(
        string='Paste redirected URL',
        help="After approving, your browser lands on a localhost URL that won't "
             "load — copy it from the address bar and paste it here (the full URL, "
             "or just the ?code=…&state=… part, or the bare code).")
    listening = fields.Boolean(
        readonly=True,
        help="A local loopback callback server is capturing the redirect — the "
             "dialog auto-completes once you approve; paste-back is the fallback.")
    info = fields.Text(readonly=True)

    def _cred_dict(self):
        return self.credential_id._as_cred_dict()

    def _redirect_uri(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return (base or '').rstrip('/') + '/ai/oauth/callback'

    def action_start(self):
        self.ensure_one()
        from ..tools import oauth
        from ..tools.http_client import AiHttpError
        self.env['ai.connector']._apply_outbound_policy()
        cred = self._cred_dict()
        try:
            if self.auth_type == 'oauth_device_code':
                flavor = cred.get('oauth_flavor')
                if flavor == 'openai_codex':
                    self._require(cred, ['oauth_device_authorization_url',
                                         'oauth_token_url', 'oauth_client_id'])
                    resp = oauth.codex_device_start(cred)
                elif flavor == 'minimax':
                    # User-code flow: the request goes to the authorize URL, not a
                    # device-authorization URL; the verifier is needed at poll time.
                    self._require(cred, ['oauth_auth_url', 'oauth_token_url', 'oauth_client_id'])
                    resp = oauth.minimax_start(cred)
                    self.credential_id.sudo().write(
                        {'oauth_code_verifier': resp.get('code_verifier')})
                elif flavor == 'qwen':
                    self._require(cred, ['oauth_device_authorization_url',
                                         'oauth_token_url', 'oauth_client_id'])
                    resp = oauth.qwen_device_start(cred)
                    self.credential_id.sudo().write(
                        {'oauth_code_verifier': resp.get('code_verifier')})
                else:
                    self._require(cred, ['oauth_device_authorization_url',
                                         'oauth_token_url', 'oauth_client_id'])
                    resp = oauth.device_code_start(cred)
                self.write({
                    # 'device_code' holds the poll handle: Codex device_auth_id,
                    # Qwen device_code, or (for MiniMax, which has none) the user_code
                    # as a non-empty marker so the auto-poll widget activates.
                    'device_code': (resp.get('device_code') or resp.get('device_auth_id')
                                    or resp.get('user_code')),
                    'user_code': resp.get('user_code'),
                    'verification_uri': resp.get('verification_uri') or resp.get('verification_url'),
                    'device_status': _('Open the Verification URL and enter the User Code — '
                                       'this dialog connects automatically once you approve.'),
                })
            elif self.auth_type == 'oauth_external':
                # OIDC discovery (xAI): resolve authorize/token endpoints from the
                # provider's .well-known doc and persist them so refresh works too.
                if cred.get('oauth_discovery_url'):
                    disc = oauth.discover_oidc(cred['oauth_discovery_url'],
                                               proxy_url=cred.get('proxy_url'))
                    vals = {k: v for k, v in disc.items() if v}
                    if vals:
                        self.credential_id.sudo().write(vals)
                        cred = self._cred_dict()
                self._require(cred, ['oauth_auth_url', 'oauth_token_url', 'oauth_client_id'])
                redirect_uri = cred.get('oauth_redirect_uri') or self._redirect_uri()
                state = secrets.token_urlsafe(24)
                url, verifier = oauth.external_auth_url(cred, redirect_uri, state)
                # Bind the flow to the initiating user so the public callback
                # only accepts completion from this same manager.
                self.credential_id.sudo().write({'oauth_state': state,
                                                 'oauth_code_verifier': verifier,
                                                 'oauth_flow_uid': self.env.uid})
                listening = self._start_loopback(redirect_uri, state)
                if listening:
                    info = _("1. Open the Authorization URL below and approve access.\n"
                             "2. This dialog completes AUTOMATICALLY once you approve "
                             "(a local listener captures the redirect).\n"
                             "If auto-capture doesn't fire, paste the redirected URL below.")
                else:
                    info = _("1. Open the Authorization URL below and approve access.\n"
                             "2. Your browser will redirect to a localhost URL that won't "
                             "load — copy that whole URL from the address bar.\n"
                             "3. Paste it into \"Paste redirected URL\" and click Submit.")
                self.write({'auth_url': url, 'listening': listening, 'info': info})
            else:
                raise UserError(_("This credential is not an OAuth provider."))
        except AiHttpError as exc:
            raise UserError(_("OAuth setup failed: %s", exc))
        return self._reopen()

    def _require(self, cred, field_keys):
        """Raise a friendly UserError listing any missing OAuth config fields."""
        labels = {
            'oauth_auth_url': _('Authorization URL'),
            'oauth_token_url': _('Token URL'),
            'oauth_client_id': _('OAuth Client ID'),
            'oauth_device_authorization_url': _('Device Authorization URL'),
        }
        missing = [labels.get(k, k) for k in field_keys if not cred.get(k)]
        if missing:
            raise UserError(_(
                "Fill in these OAuth fields on the credential first, then click Start:\n• %s\n\n"
                "(OAuth providers need your own OAuth app's client id and endpoints — "
                "they aren't shipped with the connector.)",
                '\n• '.join(missing)))

    def _start_loopback(self, redirect_uri, state):
        """Try to capture the OAuth redirect on its loopback host/port.

        Returns True if a listener is bound (auto-capture active); False means
        the user completes via paste-back (always available)."""
        from urllib.parse import urlparse
        from ..tools import oauth_loopback
        u = urlparse(redirect_uri or '')
        host = u.hostname or ''
        if not oauth_loopback.is_loopback(host) or not u.port:
            return False
        return oauth_loopback.start(state, host, u.port, u.path or '/', timeout=600)

    def _clear_flow(self):
        self.credential_id.sudo().write({
            'oauth_state': False, 'oauth_code_verifier': False, 'oauth_flow_uid': False})

    def _complete_external(self, parsed):
        """Finish a PKCE/auth-code flow from a parsed callback (paste or loopback).

        Validates state (constant-time), exchanges the code for tokens, stores
        them, clears one-time flow state, and stops the loopback listener."""
        from ..tools import oauth, oauth_loopback
        from ..tools.http_client import AiHttpError
        if parsed.get('error'):
            self._clear_flow()
            raise UserError(_("Authorization was denied: %s%s", parsed['error'],
                              (' — ' + parsed['error_description'])
                              if parsed.get('error_description') else ''))
        code = parsed.get('code')
        if not code:
            raise UserError(_("No authorization code found in the callback."))
        expected = self.credential_id.sudo().oauth_state
        if parsed.get('state') and expected and not hmac.compare_digest(parsed['state'], expected):
            self._clear_flow()
            raise UserError(_("State mismatch — restart the flow (possible CSRF or stale URL)."))
        cred = self._cred_dict()
        redirect_uri = cred.get('oauth_redirect_uri') or self._redirect_uri()
        verifier = self.credential_id.sudo().oauth_code_verifier
        if not verifier:
            # The PKCE verifier is generated at Start and wiped after any
            # completed/failed flow. If it's gone, this wizard is stale (e.g. a
            # prior failed attempt) — the code CANNOT be exchanged without it,
            # and proceeding would send code_verifier=null which Anthropic
            # rejects as "Invalid request format" (looks like the old bug but
            # isn't). Make the user restart cleanly instead.
            raise UserError(_(
                "This sign-in session has expired. Click \"Restart\", approve "
                "access again, then paste the fresh code (it's valid for ~1 min)."))
        try:
            # Anthropic requires `state` echoed in the token-exchange body; pass
            # the callback's state (else the one we stored at authorize time).
            result = oauth.exchange_code(cred, code, verifier, redirect_uri,
                                         state=parsed.get('state') or expected)
        except AiHttpError as exc:
            self._clear_flow()
            raise UserError(_(
                "Token exchange failed: %s\n\nClick \"Restart\" and complete the "
                "approval quickly — the authorization code expires within a minute.",
                exc))
        self.credential_id._apply_token_updates(result)
        self.credential_id.sudo().write({'state': 'connected'})
        self._clear_flow()
        if expected:
            oauth_loopback.cancel(expected)
        self.write({'connected': True, 'listening': False,
                    'info': _('Connected! Tokens stored.')})
        return {'type': 'ir.actions.act_window_close'}

    def action_poll(self):
        self.ensure_one()
        from ..tools import oauth, oauth_loopback
        from ..tools.http_client import AiHttpError
        # External/PKCE flow with an active loopback listener: check for a
        # captured redirect and complete automatically when it arrives.
        if self.auth_type == 'oauth_external':
            if not self.listening:
                raise UserError(_("Start the flow first."))
            state = self.credential_id.sudo().oauth_state
            parsed = oauth_loopback.result(state) if state else None
            if not parsed:
                return self._reopen()  # still waiting for the browser redirect
            self.env['ai.connector']._apply_outbound_policy()
            return self._complete_external(parsed)
        if self.auth_type != 'oauth_device_code' or not self.device_code:
            raise UserError(_("Start the device flow first."))
        self.env['ai.connector']._apply_outbound_policy()
        cred = self._cred_dict()
        flavor = cred.get('oauth_flavor')
        verifier = self.credential_id.sudo().oauth_code_verifier
        try:
            if flavor == 'openai_codex':
                result = oauth.codex_device_poll(cred, self.device_code, self.user_code)
            elif flavor == 'minimax':
                result = oauth.minimax_poll(cred, self.user_code, verifier)
            elif flavor == 'qwen':
                result = oauth.qwen_device_poll(cred, self.device_code, verifier)
            else:
                result = oauth.device_code_poll(cred, self.device_code)
        except AiHttpError as exc:
            raise UserError(_("OAuth polling failed: %s", exc))
        if result.get('pending'):
            self.device_status = _('Still pending (%s) — waiting for you to approve…',
                                   result['pending'])
            return self._reopen()
        # Qwen returns a resource_url that pins the per-account inference base.
        qwen_base = result.pop('qwen_base_url', None)
        self.credential_id._apply_token_updates(result)
        vals = {'state': 'connected', 'oauth_code_verifier': False}
        if qwen_base:
            vals['base_url'] = qwen_base
        self.credential_id.sudo().write(vals)
        self.write({'device_status': _('Connected! Tokens stored.'), 'connected': True})
        # Auto-close the dialog (the auto-poll widget and the manual button both
        # land here); a soft reload refreshes the credential form behind it.
        return {'type': 'ir.actions.act_window_close'}

    def action_submit_callback(self):
        """Complete the auth-code/PKCE flow from a manually-pasted redirect URL."""
        self.ensure_one()
        from ..tools import oauth
        if self.auth_type != 'oauth_external':
            raise UserError(_("This credential does not use the redirect/paste flow."))
        if not self.callback_url:
            raise UserError(_("Paste the redirected URL (or the code) first, then Submit."))
        self.env['ai.connector']._apply_outbound_policy()
        return self._complete_external(oauth.parse_callback(self.callback_url))

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('OAuth Setup'),
            'res_model': 'ai.oauth.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
