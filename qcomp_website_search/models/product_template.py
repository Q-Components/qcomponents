from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Make /shop searches faster by not translating these fields. The
    # ORM uses CTEs to translate which cannot be efficiently
    # searched.
    name = fields.Char('Name', index='trigram', required=True, translate=True)
    description_sale = fields.Text(
        'Sales Description', translate=True,
        help="A description of the Product that you want to communicate to your customers. "
             "This description will be copied to every Sales Order, Delivery Order and Customer Invoice/Credit Note")
