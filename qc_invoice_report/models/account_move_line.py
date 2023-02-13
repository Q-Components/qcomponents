from odoo import models, fields, api, _


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    origin = fields.Char(string='Origin',related='move_id.ref',store=True)
    mfg = fields.Char(string='MFG',related='product_id.x_studio_package',store=True)
    supplier_name = fields.Char(string='Supplier',related='product_id.supplier_name',store=True)
    sku_location = fields.Char(string='SKU Location',related='product_id.sku_location',store=True)
    condition = fields.Char(string='Condition',related='product_id.x_studio_condition_1',store=True)
    move_type = fields.Selection(string='Type',related='move_id.type',store=True)
