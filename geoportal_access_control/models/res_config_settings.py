# location_checker/models/res_config_settings.py
from odoo import models, fields,api,_
import json
import ast

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    not_allowed_country_ids  = fields.Many2many(
        'res.country', string="Not Allowed Countries", 
        help="Countries where the website is not available."
    )
    not_allowed_state_ids  = fields.Many2many(
        'res.country.state', string="Not Allowed States", 
        help="States where the website is not available."
    )
    custom_msg = fields.Char( string="Warning Msg", config_parameter ='geoportal_access_control.custom_msg')
    ip_monitor_enabled = fields.Boolean(
        string="Enable IP Request Monitoring",
        config_parameter='geoportal_access_control.ip_monitor_enabled')
    ip_monitor_window_minutes = fields.Integer(
        string="Check Window (minutes)", default=30,
        config_parameter='geoportal_access_control.ip_monitor_window_minutes')
    ip_monitor_max_requests = fields.Integer(
        string="Max Requests Before Block", default=100,
        config_parameter='geoportal_access_control.ip_monitor_max_requests')
    ip_monitor_url_patterns = fields.Char(
        string="URLs To Monitor",
        config_parameter='geoportal_access_control.ip_monitor_url_patterns')
    
    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        params = self.env['ir.config_parameter'].sudo()
        res.update( 
            not_allowed_country_ids= [(6,0,json.loads(params.get_param('geoportal_access_control.not_allowed_country_ids',"[]")))] ,
            not_allowed_state_ids= [(6,0,json.loads(params.get_param('geoportal_access_control.not_allowed_state_ids',"[]")))] ,
   
        )
        return res

    def set_values(self):
        super().set_values()
        IrConfigParameter = self.env['ir.config_parameter'].sudo()
        IrConfigParameter.set_param("geoportal_access_control.not_allowed_country_ids", self.not_allowed_country_ids.ids)
        IrConfigParameter.set_param("geoportal_access_control.not_allowed_state_ids", self.not_allowed_state_ids.ids)
    
