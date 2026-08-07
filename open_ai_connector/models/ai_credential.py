# -*- coding: utf-8 -*-
"""ai.credential — stored auth state for a provider.

Holds the actual secrets (API key / AWS creds / OAuth tokens), persisted in the
Odoo database and restricted to the AI Manager group.
"""
import logging
from datetime import datetime, timezone

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)
MGR = 'open_ai_connector.group_ai_manager'


class AiCredential(models.Model):
    _name = 'ai.credential'
    _description = 'AI Credential'
    _inherit = ['mail.thread']
    _order = 'provider_id, sequence, id'

    name = fields.Char(string='Name', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    provider_id = fields.Many2one(
        'ai.provider', string='Provider', required=True, ondelete='cascade', index=True)
    provider_code = fields.Char(related='provider_id.code', store=True, index=True)
    api_mode = fields.Selection(related='provider_id.api_mode')
    auth_type = fields.Selection(related='provider_id.auth_type', store=True)
    company_id = fields.Many2one(
        'res.company', string='Company', index=True,
        default=lambda self: self.env.company)
    is_default = fields.Boolean(
        string='Default', help="Use this credential when none is specified for the provider.")
    state = fields.Selection(
        [('draft', 'Not Tested'), ('connected', 'Connected'), ('error', 'Error')],
        default='draft', tracking=True)
    last_test_message = fields.Char(readonly=True)
    last_tested = fields.Datetime(string='Last Tested', readonly=True)
    model_count = fields.Integer(string='Models', compute='_compute_model_count')

    @api.depends('provider_id', 'provider_id.model_ids')
    def _compute_model_count(self):
        for rec in self:
            rec.model_count = len(rec.provider_id.model_ids)

    def action_view_models(self):
        self.ensure_one()
        return self.provider_id.action_view_models()

    # ── API key path ──────────────────────────────────────────────────
    api_key = fields.Char(string='API Key', groups=MGR)
    base_url = fields.Char(
        string='Base URL Override', groups=MGR,
        help="Required for providers with no fixed endpoint (Custom / Azure Foundry).")
    extra_headers = fields.Text(string='Extra Headers (JSON)', groups=MGR)
    proxy_url = fields.Char(string='Proxy URL', groups=MGR)

    # ── AWS path ──────────────────────────────────────────────────────
    aws_access_key_id = fields.Char(string='AWS Access Key ID', groups=MGR)
    aws_secret_access_key = fields.Char(string='AWS Secret Access Key', groups=MGR)
    aws_session_token = fields.Char(string='AWS Session Token', groups=MGR)
    aws_region = fields.Char(string='AWS Region', default='us-east-1')

    # ── OAuth path ────────────────────────────────────────────────────
    oauth_client_id = fields.Char(string='OAuth Client ID')
    oauth_client_secret = fields.Char(string='OAuth Client Secret', groups=MGR)
    # Routing URLs are manager-only (parity with base_url): they decide where
    # tokens are sent/exchanged, so they shouldn't be visible/editable by AI users.
    oauth_auth_url = fields.Char(string='Authorization URL', groups=MGR)
    oauth_token_url = fields.Char(string='Token URL', groups=MGR)
    oauth_device_authorization_url = fields.Char(string='Device Authorization URL', groups=MGR)
    oauth_scopes = fields.Char(string='Scopes')
    oauth_access_token = fields.Char(string='Access Token', groups=MGR)
    oauth_refresh_token = fields.Char(string='Refresh Token', groups=MGR)
    oauth_token_expiry = fields.Datetime(string='Token Expiry')
    # Transient PKCE / device-flow state (set during the OAuth wizard).
    oauth_state = fields.Char(string='OAuth State', groups=MGR)
    oauth_code_verifier = fields.Char(string='PKCE Verifier', groups=MGR)
    oauth_flow_uid = fields.Many2one(
        'res.users', string='OAuth Flow Initiator', groups=MGR,
        help="User who started the current OAuth authorization. The public "
             "callback only completes the flow for this same user.")
    # Google Cloud Code Assist (Gemini CLI): the GCP project sent in every
    # inference request. Leave blank for personal/free-tier accounts — it's
    # discovered (and cached here) on first use; set it explicitly to pin a
    # paid GCP project.
    gemini_project_id = fields.Char(string='GCP Project (Gemini CLI)', groups=MGR)

    @api.onchange('provider_id')
    def _onchange_provider_oauth_defaults(self):
        """Pre-fill OAuth endpoints from the provider's seeded defaults (editable).

        So users of OAuth providers (OpenAI Codex, Qwen, Gemini-CLI, Nous,
        MiniMax) don't have to hunt for client id / endpoints — they auto-fill.
        """
        p = self.provider_id
        if not p or p.auth_type not in ('oauth_external', 'oauth_device_code'):
            return
        self.oauth_client_id = self.oauth_client_id or p.oauth_client_id
        self.oauth_client_secret = self.oauth_client_secret or p.oauth_client_secret
        self.oauth_auth_url = self.oauth_auth_url or p.oauth_auth_url
        self.oauth_token_url = self.oauth_token_url or p.oauth_token_url
        self.oauth_device_authorization_url = (
            self.oauth_device_authorization_url or p.oauth_device_authorization_url)
        self.oauth_scopes = self.oauth_scopes or p.oauth_scopes

    # ── Helpers ───────────────────────────────────────────────────────
    def _as_cred_dict(self):
        """Plain dict (with secrets, sudo-read) for the tools/ auth layer."""
        self.ensure_one()
        rec = self.sudo()
        prov = rec.provider_id  # OAuth endpoints fall back to the provider's seeded defaults
        expiry = rec.oauth_token_expiry
        expiry_iso = None
        if expiry:
            # Odoo Datetime is naive UTC — mark it tz-aware for the OAuth layer.
            expiry_iso = expiry.replace(tzinfo=timezone.utc).isoformat()
        return {
            'api_key': rec.api_key or '',
            'base_url': rec.base_url or '',
            'extra_headers': rec.extra_headers or '',
            'proxy_url': rec.proxy_url or '',
            'aws_access_key_id': rec.aws_access_key_id or '',
            'aws_secret_access_key': rec.aws_secret_access_key or '',
            'aws_session_token': rec.aws_session_token or '',
            'aws_region': rec.aws_region or 'us-east-1',
            'oauth_client_id': rec.oauth_client_id or prov.oauth_client_id or '',
            'oauth_client_secret': rec.oauth_client_secret or prov.oauth_client_secret or '',
            'oauth_auth_url': rec.oauth_auth_url or prov.oauth_auth_url or '',
            'oauth_token_url': rec.oauth_token_url or prov.oauth_token_url or '',
            'oauth_device_authorization_url': (rec.oauth_device_authorization_url
                                               or prov.oauth_device_authorization_url or ''),
            'oauth_scopes': rec.oauth_scopes or prov.oauth_scopes or '',
            'oauth_redirect_uri': prov.oauth_redirect_uri or '',
            'oauth_extra_authorize_params': prov.get_oauth_extra_authorize_params(),
            'oauth_flavor': prov.oauth_flavor or 'standard',
            'oauth_discovery_url': prov.oauth_discovery_url or '',
            'oauth_access_token': rec.oauth_access_token or '',
            'oauth_refresh_token': rec.oauth_refresh_token or '',
            'oauth_token_expiry': expiry_iso,
        }

    @staticmethod
    def _parse_iso_to_naive_utc(iso_str):
        try:
            dt = datetime.fromisoformat(iso_str)
        except (ValueError, TypeError):
            return False
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    def _apply_token_updates(self, updates):
        """Write back refreshed OAuth token fields (maps ISO expiry -> Datetime)."""
        if not updates:
            return
        vals = {}
        for key in ('oauth_access_token', 'oauth_refresh_token'):
            if updates.get(key):
                vals[key] = updates[key]
        if updates.get('oauth_token_expiry'):
            dt = self._parse_iso_to_naive_utc(updates['oauth_token_expiry'])
            if dt:
                vals['oauth_token_expiry'] = dt
        if vals:
            self.sudo().write(vals)

    def _ensure_oauth_fresh(self, lead_seconds=None):
        """Refresh the access token if it is stale (OAuth providers only).

        Concurrency-safe: when a refresh is needed, take a row lock on this
        credential (``SELECT … FOR UPDATE``) so two Odoo workers can't refresh
        the same token at once. That race is dangerous because some providers
        (OpenAI Codex, etc.) ROTATE the refresh_token on use — two concurrent
        refreshes would invalidate each other and brick the credential. After
        acquiring the lock we re-read and re-check: a sibling worker may have
        just refreshed while we waited, in which case we do nothing.

        *lead_seconds* lets the proactive cron refresh ahead of expiry; the
        reactive (per-call) path uses the default just-in-time skew.
        """
        self.ensure_one()
        if self.auth_type not in ('oauth_external', 'oauth_device_code'):
            return
        from ..tools import oauth
        self.env['ai.connector']._apply_outbound_policy()
        if not oauth.needs_refresh(self._as_cred_dict(), lead_seconds):
            return  # fast path: still fresh, no lock needed
        # Serialize refresh across workers, then double-check under the lock.
        self.env.cr.execute(
            "SELECT id FROM ai_credential WHERE id = %s FOR UPDATE", (self.id,))
        self.invalidate_recordset(
            ['oauth_access_token', 'oauth_refresh_token', 'oauth_token_expiry'])
        if not oauth.needs_refresh(self._as_cred_dict(), lead_seconds):
            return  # another worker refreshed while we held/awaited the lock
        updates = oauth.refresh(self._as_cred_dict())
        self._apply_token_updates(updates)

    @api.model
    def _cron_refresh_oauth_tokens(self, lead_seconds=900):
        """Proactively refresh OAuth tokens before they expire (scheduled).

        A background refresh loop: instead of paying a
        token-refresh latency spike on the first call after expiry — and
        instead of letting an unused refresh_token lapse — refresh anything
        expiring within *lead_seconds* (default 15 min) on a timer. The
        reactive per-call refresh remains the backstop for anything missed.
        """
        from ..tools import oauth
        creds = self.sudo().search([
            ('auth_type', 'in', ('oauth_external', 'oauth_device_code')),
            ('active', '=', True),
        ])
        refreshed = 0
        for cred in creds:
            if not oauth.needs_refresh(cred._as_cred_dict(), lead_seconds):
                continue
            try:
                with self.env.cr.savepoint():
                    cred._ensure_oauth_fresh(lead_seconds=lead_seconds)
                refreshed += 1
            except Exception as exc:  # noqa: BLE001 - one bad token must not stop the batch
                _logger.warning(
                    "Proactive OAuth refresh failed for credential %s (%s): %s",
                    cred.name, cred.id, exc)
        if refreshed:
            _logger.info("Proactive OAuth refresh: %s credential(s) refreshed.", refreshed)
        return refreshed

    def _ensure_gemini_project(self, access_token, timeout=30.0):
        """Resolve (and cache) the GCP project for the Gemini CLI / Code Assist
        envelope. Returns the configured project as-is, else discovers it via
        Google's loadCodeAssist/onboardUser and persists it for next time.

        Caller must have applied the outbound SSRF policy already (chat() does).
        Discovery failures are non-fatal — Google may still accept an empty
        project for fresh free-tier accounts, and the connector surfaces any
        real error from the inference call itself.
        """
        self.ensure_one()
        rec = self.sudo()
        if rec.gemini_project_id:
            return rec.gemini_project_id
        if not access_token:
            return ''
        from ..tools import gemini_cloudcode
        try:
            project = gemini_cloudcode.resolve_project_id(access_token, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - never block a chat on discovery
            _logger.info("Gemini CLI project discovery failed (%s): %s", rec.name, exc)
            return ''
        if project:
            rec.write({'gemini_project_id': project})
        return project or ''

    # ── Buttons ───────────────────────────────────────────────────────
    def action_test_connection(self):
        self.ensure_one()
        try:
            self._ensure_oauth_fresh()
            result = self.env['ai.connector'].chat(
                provider=self.provider_id,
                model=self._default_test_model(),
                messages=[{'role': 'user', 'content': 'ping'}],
                credential=self, max_tokens=16, log=False,
            )
            self.write({'state': 'connected', 'last_tested': fields.Datetime.now(),
                        'last_test_message': _('OK — %s', (result.get('content') or '')[:80])})
            self.message_post(body=_("Connection test OK."))
        except Exception as exc:  # noqa: BLE001 - surface any provider error to the user
            self.write({'state': 'error', 'last_tested': fields.Datetime.now(),
                        'last_test_message': str(exc)[:250]})
            raise UserError(_("Connection test failed:\n%s", exc))
        return self._reload_notification(_("Connection successful."))

    def _default_test_model(self):
        """Pick a sensible model for a ping. Prefer the provider's declared aux
        model, then its curated fallback (a known-good general model), then the
        first catalog entry — the catalog's alphabetical first can be a
        specialised model (e.g. codex 'codex-auto-review') that rejects a chat."""
        self.ensure_one()
        prov = self.provider_id
        if prov.default_aux_model:
            return prov.default_aux_model
        fallback = prov.get_fallback_models()
        if fallback:
            return fallback[0]
        if prov.model_ids:
            return prov.model_ids[0].model_id
        return 'gpt-4o-mini'

    def action_fetch_models(self):
        self.ensure_one()
        from ..tools.http_client import AiHttpError
        try:
            self._ensure_oauth_fresh()
            added, total = self.provider_id._fetch_models_with_credential(self)
        except AiHttpError as exc:
            raise UserError(_("Could not fetch models: %s", exc))
        return self._reload_notification(
            _("%(total)s model(s) available (%(added)s new).", total=total, added=added))

    def action_oauth_start(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('OAuth Setup'),
            'res_model': 'ai.oauth.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_credential_id': self.id},
        }

    def _reload_notification(self, message):
        return self._reload_notification_static(message)

    @api.model
    def _reload_notification_static(self, message):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'message': message, 'type': 'success',
                       # soft_reload is a client-action TAG, not a type.
                       'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}},
        }
