# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ai_connector_bridge_enabled = fields.Boolean(
        string='Route Odoo AI through Connector',
        config_parameter='ai_connector_bridge.enabled',
        help="When ON, Odoo's native AI (Agents, AI fields, AI server actions) "
             "routes through the AI Connector using the Provider / Account / "
             "Model chosen below (or the gateway Default Provider/Model if left "
             "blank). OFF = stock Odoo AI.")
    ai_bridge_provider_id = fields.Many2one(
        'ai.provider', string='Odoo AI Provider',
        config_parameter='ai_connector_bridge.provider_id',
        domain="[('credential_ids.state', '=', 'connected')]",
        help="Which connector provider Odoo's native AI should use. "
             "Only providers with a connected credential are listed.")
    ai_bridge_credential_id = fields.Many2one(
        'ai.credential', string='Odoo AI Account',
        config_parameter='ai_connector_bridge.credential_id',
        domain="[('provider_id', '=', ai_bridge_provider_id), ('state', '=', 'connected')]",
        help="Which account/credential to use (you may have several per "
             "provider). Leave blank to use the provider's default credential.")
    ai_bridge_model_id = fields.Many2one(
        'ai.model', string='Odoo AI Model',
        domain="[('provider_id', '=', ai_bridge_provider_id), ('is_image_model', '=', False)]",
        help="Model Odoo's native AI should call. Pick from the provider's "
             "fetched chat models (image-generation models are excluded).")

    @api.onchange('ai_bridge_provider_id')
    def _onchange_bridge_provider(self):
        for s in self:
            if s.ai_bridge_credential_id.provider_id != s.ai_bridge_provider_id:
                s.ai_bridge_credential_id = False
            if s.ai_bridge_model_id.provider_id != s.ai_bridge_provider_id:
                s.ai_bridge_model_id = False

    @api.model
    def get_values(self):
        res = super().get_values()
        icp = self.env['ir.config_parameter'].sudo()
        model_str = icp.get_param('ai_connector_bridge.model')
        model = self.env['ai.model']
        if model_str:
            domain = [('model_id', '=', model_str), ('is_image_model', '=', False)]
            prov_id = res.get('ai_bridge_provider_id')
            if prov_id:
                domain.append(('provider_id', '=', prov_id))
            model = model.search(domain, limit=1)
        res['ai_bridge_model_id'] = model.id
        return res

    def set_values(self):
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            'ai_connector_bridge.model', self.ai_bridge_model_id.model_id or '')
