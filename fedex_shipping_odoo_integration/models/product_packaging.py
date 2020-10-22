from odoo import fields, models, api
class ProductPackagingClass(models.Model):
    _inherit = 'product.packaging'
    package_carrier_type = fields.Selection(selection_add=[('fedex_shipping_provider', 'Fedex')])
