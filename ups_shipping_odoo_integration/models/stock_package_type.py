from odoo import fields, models, api

class ProductPackaging(models.Model):
    _inherit = 'stock.package.type'
    package_carrier_type = fields.Selection(selection_add=[('ups_shipping_provider', 'UPS')],ondelete={'ups_shipping_provider': 'set default'})
