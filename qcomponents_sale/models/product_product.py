from odoo import api, fields, models, _

class ProductProduct(models.Model):
    _inherit = "product.product"

    x_studio_field_2dpeg = fields.Float(string='Quotation Price', digits='Product Price')
    sku_location = fields.Char(string='Sku Location')
    x_studio_condition_1 = fields.Char(string='Condition')
    supplier_name = fields.Char(string='Supplier Name')