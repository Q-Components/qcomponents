from odoo import api, fields, models, _

class ProductProduct(models.Model):
    _inherit = "product.product"

    x_studio_field_2dpeg = fields.Float(string='Quotation Price', digits='Product Price')
