from odoo import api, fields, models, _

class ProductProduct(models.Model):
    _inherit = "product.product"

    quotation_price = fields.Float(string='Quotation Price', digits='Product Price')
