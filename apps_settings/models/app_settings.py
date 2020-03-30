from odoo import api, fields, models ,_

class apps_setting(models.Model):
    
    _inherit = 'ir.module.module'
    
    def _button_immediate_function(self, function):
        res = super(apps_setting,self)._button_immediate_function(function = function)
        return True
