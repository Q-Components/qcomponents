from odoo import models, fields, api, _
from datetime import datetime

class ResCompany(models.Model):    
    _inherit="res.company"
    
    auto_generate_invoice = fields.Boolean(string='Auto Generate Invoice While Validate Picking')
    invoice_generated_on = fields.Selection([('draft','Draft'),('open','Open'),('paid','Paid')],string="Invoice Generated On",default='draft')