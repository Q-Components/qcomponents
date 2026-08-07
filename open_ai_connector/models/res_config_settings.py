# -*- coding: utf-8 -*-
"""Settings: default provider/model for the gateway, gateway enable.

The gateway reads the model as a plain id string (``open_ai_connector.default_model``),
but the UI offers a Many2one picker over the chosen provider's fetched models —
so we resolve that param ↔ ``ai.model`` in get_values/set_values.
"""
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ai_default_provider_id = fields.Many2one(
        'ai.provider', string='Default AI Provider',
        config_parameter='open_ai_connector.default_provider_id',
        domain="[('credential_ids.state', '=', 'connected')]",
        help="Gateway provider used when a request's model has no provider prefix. "
             "Only providers with a connected credential are listed.")
    ai_default_model_id = fields.Many2one(
        'ai.model', string='Default AI Model',
        domain="[('provider_id', '=', ai_default_provider_id), ('is_image_model', '=', False)]",
        help="Model the gateway uses when the request omits one. "
             "Pick from the selected provider's fetched models "
             "(use Fetch Models on its credential to populate the list).")
    ai_gateway_enabled = fields.Boolean(
        string='Enable HTTP Gateway', default=True,
        config_parameter='open_ai_connector.gateway_enabled',
        help="Expose the OpenAI-compatible /ai/v1/chat/completions endpoint.")
    ai_gateway_rate_limit = fields.Integer(
        string='Gateway Rate Limit', default=120,
        config_parameter='open_ai_connector.gateway_rate_limit_per_min',
        help="Max gateway calls per user per minute (counted from usage logs). "
             "0 disables the limit.")
    ai_gateway_max_tokens = fields.Integer(
        string='Gateway Max Output Tokens', default=0,
        config_parameter='open_ai_connector.gateway_max_tokens',
        help="Hard ceiling clamped onto max_tokens for gateway requests. "
             "0 means no clamp.")
    ai_block_private_endpoints = fields.Boolean(
        string='Block Private/Loopback Endpoints',
        config_parameter='open_ai_connector.block_private_endpoints',
        help="Refuse outbound calls to loopback (127.0.0.1) and private "
             "(10/172.16/192.168) addresses. Leave OFF if you use a local "
             "provider such as Ollama/vLLM. Cloud metadata + link-local are "
             "ALWAYS blocked regardless.")
    ai_outbound_allowlist = fields.Char(
        string='Outbound Host Allowlist',
        config_parameter='open_ai_connector.outbound_host_allowlist',
        help="Comma/space-separated EXTRA hostnames or parent domains the server "
             "may call (e.g. an internal gateway). When set, other hosts are "
             "refused — EXCEPT every domain used by the connector's own providers "
             "for models and authentication (inference, OAuth/login, model-fetch), "
             "which are ALWAYS allowed automatically so auth never breaks. "
             "Empty = allow any (except the always-blocked metadata/link-local ranges).")

    ai_gateway_base_url = fields.Char(
        string='Gateway Base URL', readonly=True, compute='_compute_gateway_info',
        help="OpenAI-compatible base URL to paste into other apps/SDKs. Use an "
             "Odoo API key as the bearer token (Preferences → Account Security → "
             "New API Key). Models are 'provider/model', e.g. xai-oauth/grok-4.")
    ai_gateway_curl = fields.Text(
        string='Example request', readonly=True, compute='_compute_gateway_info')

    @api.depends('ai_gateway_enabled')
    def _compute_gateway_info(self):
        base = (self.env['ir.config_parameter'].sudo().get_param('web.base.url') or '').rstrip('/')
        db = self.env.cr.dbname
        base_url = (base + '/ai/v1') if base else '/ai/v1'
        # This server hosts several databases, so stateless bearer calls must name
        # the DB (?db=) unless the host already maps to a single database.
        curl = (
            'curl "%(base)s/chat/completions?db=%(db)s" \\\n'
            '  -H "Authorization: Bearer <YOUR_ODOO_API_KEY>" \\\n'
            '  -H "Content-Type: application/json" \\\n'
            '  -d \'{"model": "xai-oauth/grok-4", '
            '"messages": [{"role": "user", "content": "hi"}]}\''
        ) % {'base': base_url, 'db': db}
        for s in self:
            s.ai_gateway_base_url = base_url
            s.ai_gateway_curl = curl

    @api.onchange('ai_default_provider_id')
    def _onchange_provider_reset_model(self):
        # Drop a stale model selection when it no longer belongs to the provider.
        for s in self:
            if s.ai_default_model_id.provider_id != s.ai_default_provider_id:
                s.ai_default_model_id = False

    @api.model
    def get_values(self):
        res = super().get_values()
        icp = self.env['ir.config_parameter'].sudo()
        model_str = icp.get_param('open_ai_connector.default_model')
        model = self.env['ai.model']
        if model_str:
            domain = [('model_id', '=', model_str), ('is_image_model', '=', False)]
            prov_id = res.get('ai_default_provider_id')
            if prov_id:
                domain.append(('provider_id', '=', prov_id))
            model = model.search(domain, limit=1)
        res['ai_default_model_id'] = model.id
        return res

    def set_values(self):
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            'open_ai_connector.default_model',
            self.ai_default_model_id.model_id or '')
