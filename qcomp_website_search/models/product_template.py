from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Make /shop searches faster by not translating these fields. The
    # ORM uses CTEs to translate which cannot be efficiently
    # searched.
    name = fields.Char(translate=True)
    description = fields.Text(translate=True)
    description_sale = fields.Text(translate=True)
