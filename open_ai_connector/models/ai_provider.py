# -*- coding: utf-8 -*-
"""ai.provider — declarative provider catalog.

A declarative profile describing one inference provider.
Each record declares everything about one inference provider in one place:
auth type, endpoints, wire protocol (api_mode) and request quirks. Every
other layer (credentials, transports, the gateway) reads from these records
instead of hard-coding provider data.
"""
import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Wire protocols (api_mode) we know how to build/parse.
API_MODES = [
    ('chat_completions', 'OpenAI Chat Completions'),
    ('anthropic_messages', 'Anthropic Messages'),
    ('bedrock_converse', 'AWS Bedrock Converse'),
    ('codex_responses', 'OpenAI Responses (Codex)'),
    ('gemini_cloudcode', 'Google Cloud Code Assist (Gemini CLI)'),
]

# Credential resolution strategies (auth_type).
AUTH_TYPES = [
    ('api_key', 'API Key'),
    ('aws_sdk', 'AWS SDK (SigV4)'),
    ('oauth_external', 'OAuth (external / PKCE)'),
    ('oauth_device_code', 'OAuth (device code)'),
    ('copilot', 'GitHub Copilot'),
    ('external_process', 'External process (ACP)'),
]


class AiProvider(models.Model):
    _name = 'ai.provider'
    _description = 'AI Provider'
    _order = 'sequence, name'

    name = fields.Char(string='Name', required=True, translate=False)
    code = fields.Char(
        string='Code', required=True, index=True,
        help="Canonical provider key, e.g. 'openrouter'. Used everywhere to "
             "reference this provider.")
    aliases = fields.Char(
        string='Aliases',
        help="Comma-separated alternative codes that resolve to this provider.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    api_mode = fields.Selection(
        API_MODES, string='API Mode', required=True, default='chat_completions',
        help="Wire protocol used to build the request and parse the response.")
    auth_type = fields.Selection(
        AUTH_TYPES, string='Auth Type', required=True, default='api_key',
        help="How credentials are resolved and attached to the request.")

    base_url = fields.Char(
        string='Base URL',
        help="Inference base URL. Blank means the credential must supply it "
             "(custom / Azure Foundry per-resource endpoints).")
    models_url = fields.Char(
        string='Models URL',
        help="Explicit model-listing endpoint. Falls back to {base_url}/models.")

    env_vars = fields.Char(
        string='Env Vars',
        help="Comma-separated environment variable names commonly used for this "
             "provider's key (informational — keys are stored on credentials here).")
    signup_url = fields.Char(string='Signup URL')

    default_headers = fields.Text(
        string='Default Headers (JSON)',
        help="JSON dict of headers applied at request construction time.")
    omit_temperature = fields.Boolean(
        string='Omit Temperature',
        help="Provider manages temperature server-side; never send it (Kimi).")
    fixed_temperature = fields.Float(
        string='Fixed Temperature',
        help="If set (>0), always send this temperature.")
    default_max_tokens = fields.Integer(
        string='Default Max Tokens',
        help="Output-token floor sent when the caller does not specify one.")
    default_aux_model = fields.Char(
        string='Default Aux Model',
        help="Cheap model used for auxiliary tasks (titles, summaries).")

    supports_vision = fields.Boolean(string='Supports Vision')
    supports_vision_tool_messages = fields.Boolean(
        string='Vision in Tool Messages', default=True)
    supports_health_check = fields.Boolean(string='Supports Health Check', default=True)
    supports_image_gen = fields.Boolean(
        string='Supports Image Generation',
        help="Provider can generate images (xAI Grok Imagine, OpenAI Codex gpt-image-2).")
    supports_video_gen = fields.Boolean(
        string='Supports Video Generation',
        help="Provider can generate videos (xAI Grok Imagine video).")
    supports_image_edit = fields.Boolean(
        string='Supports Image Edit (Remix)',
        help="Provider can edit/remix an existing image (image-to-image): OpenAI "
             "Codex via the /responses image_generation tool, or an OpenAI-compatible "
             "/images/edits endpoint. Drives the Remix button in AI Image Studio.")
    default_image_model = fields.Char(
        string='Default Image Model',
        help="Image-generation model id used by the Playground when this provider "
             "is picked in Image mode (e.g. grok-imagine-image, gpt-image-2-medium).")
    default_video_model = fields.Char(
        string='Default Video Model',
        help="Video-generation model id used by the Playground in Video mode "
             "(e.g. grok-imagine-video).")

    fallback_models = fields.Text(
        string='Fallback Models',
        help="Newline-separated curated model IDs shown when a live fetch fails.")

    # ── OAuth defaults (seeded for known OAuth providers) ──────────────
    # Auto-filled onto credentials so users don't have to hunt for them.
    oauth_client_id = fields.Char(string='OAuth Client ID (default)')
    oauth_client_secret = fields.Char(
        string='OAuth Client Secret (default)',
        groups='open_ai_connector.group_ai_manager')
    oauth_auth_url = fields.Char(string='Authorization URL (default)')
    oauth_token_url = fields.Char(string='Token URL (default)')
    oauth_device_authorization_url = fields.Char(string='Device Authorization URL (default)')
    oauth_scopes = fields.Char(string='Scopes (default)')
    oauth_redirect_uri = fields.Char(
        string='Redirect URI (default)',
        help="The (often loopback) redirect the provider's OAuth client expects, "
             "e.g. http://localhost:1455/auth/callback. The browser redirects here "
             "after sign-in; the user pastes that redirected URL back to finish — "
             "no local listener needed.")
    oauth_extra_authorize_params = fields.Text(
        string='Extra Authorize Params (JSON)',
        help="JSON dict of extra query params appended to the authorization URL "
             "(provider-specific flags, e.g. {\"prompt\": \"login\"}).")
    oauth_flavor = fields.Selection(
        [('standard', 'Standard OAuth2'),
         ('openai_codex', 'OpenAI Codex (device)'),
         ('anthropic', 'Anthropic (claude.ai OAuth)'),
         ('qwen', 'Qwen (device + PKCE)'),
         ('minimax', 'MiniMax (user code)')],
        string='OAuth Flavor', default='standard',
        help="Which OAuth dialect this provider speaks. 'standard' is RFC-6749/"
             "8628 (Gemini/xAI PKCE, form-encoded token endpoint). 'openai_codex' "
             "is OpenAI's custom JSON device flow. 'anthropic' is claude.ai's "
             "PKCE flow whose token endpoint takes/returns JSON and whose tokens "
             "authenticate inference via Bearer + anthropic-beta (not x-api-key).")
    oauth_discovery_url = fields.Char(
        string='OIDC Discovery URL (default)',
        help="OpenID Connect ``.well-known/openid-configuration`` URL. When set, "
             "the authorization/token endpoints are resolved from it at login "
             "(xAI), so they can rotate without a code change.")

    def get_oauth_extra_authorize_params(self):
        """Parse oauth_extra_authorize_params JSON into a dict (empty on error)."""
        self.ensure_one()
        if not self.oauth_extra_authorize_params:
            return {}
        try:
            data = json.loads(self.oauth_extra_authorize_params)
            return data if isinstance(data, dict) else {}
        except (ValueError, TypeError):
            _logger.warning("Invalid oauth_extra_authorize_params JSON on %s", self.code)
            return {}

    is_wired = fields.Boolean(
        string='Wired', compute='_compute_is_wired', store=True,
        help="True when this provider's api_mode/auth_type is implemented by "
             "the connector. external_process (Copilot ACP) is not wired.")

    credential_ids = fields.One2many('ai.credential', 'provider_id', string='Credentials')
    credential_count = fields.Integer(compute='_compute_counts')
    model_ids = fields.One2many('ai.model', 'provider_id', string='Models')
    model_count = fields.Integer(compute='_compute_counts')

    # v19: _sql_constraints is no longer honoured — use model.Constraint.
    _code_uniq = models.Constraint('unique(code)', 'Provider code must be unique.')

    @api.depends('api_mode', 'auth_type')
    def _compute_is_wired(self):
        wired_modes = {'chat_completions', 'anthropic_messages',
                       'bedrock_converse', 'codex_responses', 'gemini_cloudcode'}
        for p in self:
            p.is_wired = p.api_mode in wired_modes and p.auth_type != 'external_process'

    @api.depends('credential_ids', 'model_ids')
    def _compute_counts(self):
        for p in self:
            p.credential_count = len(p.credential_ids)
            p.model_count = len(p.model_ids)

    # ── Helpers ────────────────────────────────────────────────────────
    @api.model
    def _resolve(self, code):
        """Resolve a provider by code or alias. Returns a recordset (may be empty)."""
        if not code:
            return self.browse()
        code = str(code).strip()
        provider = self.search([('code', '=', code)], limit=1)
        if provider:
            return provider
        # alias match (csv contains the code as a whole token)
        for p in self.search([('aliases', '!=', False)]):
            tokens = [a.strip() for a in (p.aliases or '').split(',')]
            if code in tokens:
                return p
        return self.browse()

    def get_default_headers(self):
        """Parse the default_headers JSON into a dict (empty on error)."""
        self.ensure_one()
        if not self.default_headers:
            return {}
        try:
            data = json.loads(self.default_headers)
            return data if isinstance(data, dict) else {}
        except (ValueError, TypeError):
            _logger.warning("Invalid default_headers JSON on provider %s", self.code)
            return {}

    def get_fallback_models(self):
        self.ensure_one()
        return [m.strip() for m in (self.fallback_models or '').splitlines() if m.strip()]

    def _to_dict(self):
        """Plain dict view consumed by the (ORM-free) tools/ transport layer."""
        self.ensure_one()
        return {
            'code': self.code,
            'api_mode': self.api_mode,
            'auth_type': self.auth_type,
            'base_url': self.base_url or '',
            'models_url': self.models_url or '',
            'default_headers': self.get_default_headers(),
            'omit_temperature': self.omit_temperature,
            'fixed_temperature': self.fixed_temperature or None,
            'default_max_tokens': self.default_max_tokens or None,
            'supports_vision': self.supports_vision,
            'oauth_flavor': self.oauth_flavor or 'standard',
        }

    def action_view_credentials(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Credentials'),
            'res_model': 'ai.credential',
            'view_mode': 'list,form',
            'domain': [('provider_id', '=', self.id)],
            'context': {'default_provider_id': self.id},
        }

    def action_view_models(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Models'),
            'res_model': 'ai.model',
            'view_mode': 'list,form',
            'domain': [('provider_id', '=', self.id)],
            'context': {'default_provider_id': self.id},
        }

    def action_fetch_models(self):
        """Populate ai.model from a live catalog fetch using a default credential."""
        self.ensure_one()
        cred = self.credential_ids.filtered('is_default')[:1] or self.credential_ids[:1]
        if not cred and self.fallback_models:
            added, total = self.env['ai.model']._upsert(self, self.get_fallback_models())
            return self.env['ai.credential']._reload_notification_static(
                _("%(total)s model(s) available (%(added)s new, from fallback list).",
                  total=total, added=added))
        if not cred:
            raise UserError(_("Add a credential first, or define fallback models."))
        added, total = self._fetch_models_with_credential(cred)
        return self.env['ai.credential']._reload_notification_static(
            _("%(total)s model(s) available (%(added)s new).", total=total, added=added))

    def _fetch_models_with_credential(self, credential):
        """Live catalog fetch + upsert.

        Falls back to the curated fallback_models when the live fetch fails or
        the provider has no REST catalog (Bedrock, Copilot ACP).
        """
        self.ensure_one()
        from ..tools import http_client
        self.env['ai.connector']._apply_outbound_policy()
        model_ids = None
        # Providers with no REST /models endpoint -> straight to fallback.
        if self.auth_type in ('aws_sdk', 'external_process'):
            model_ids = None
        else:
            cred = credential.sudo()
            base = cred.base_url or self.base_url
            # Anthropic's catalog is at /v1/models (NOT /models); OpenAI-compatible
            # providers use /models.
            suffix = '/v1/models' if self.api_mode == 'anthropic_messages' else '/models'
            url = (self.models_url or '').strip() or (
                (base.rstrip('/') + suffix) if base else '')
            # Only probe real HTTP(S) endpoints. Providers with an internal
            # scheme (e.g. Gemini CLI's cloudcode-pa://) have no REST /models —
            # fall straight through to the curated fallback list.
            if url and not url.lower().startswith(('http://', 'https://')):
                url = ''
            if url:
                headers = {'Accept': 'application/json',
                           'User-Agent': 'OdooAIConnector/19.0'}
                impersonate = None
                if self.api_mode == 'anthropic_messages':
                    # Anthropic is Cloudflare-fronted (needs a browser TLS
                    # fingerprint) and OAuth (claude.ai) tokens authenticate via
                    # Bearer + anthropic-beta, NOT x-api-key — resolve the right
                    # headers per auth type so the live catalog fetch succeeds.
                    impersonate = 'chrome'
                    if self.auth_type.startswith('oauth'):
                        from ..tools import auth as _auth
                        headers.update(_auth.resolve(self._to_dict(),
                                                     cred._as_cred_dict())['headers'])
                    elif cred.api_key:
                        headers['x-api-key'] = cred.api_key
                        headers['anthropic-version'] = '2023-06-01'
                else:
                    key = (cred.oauth_access_token if self.auth_type.startswith('oauth')
                           else cred.api_key)
                    if key and self.code != 'openrouter':  # openrouter catalog is public
                        headers['Authorization'] = f'Bearer {key}'
                try:
                    data = http_client.get_json(url, headers=headers, timeout=15.0,
                                                impersonate=impersonate)
                    # Response shapes vary: OpenAI -> {"data":[{"id":..}]};
                    # OpenAI-Codex backend -> {"models":[{"slug":..}]}; some
                    # gateways return a bare list.
                    if isinstance(data, list):
                        items = data
                    elif isinstance(data, dict):
                        items = data.get('data') or data.get('models') or []
                    else:
                        items = []
                    model_ids = [m.get('id') or m.get('slug') for m in items
                                 if isinstance(m, dict) and (m.get('id') or m.get('slug'))]
                except Exception as exc:  # noqa: BLE001
                    _logger.info("fetch_models(%s) failed: %s", self.code, exc)
                    model_ids = None
        if not model_ids:
            model_ids = self.get_fallback_models()
        return self.env['ai.model']._upsert(self, model_ids)
