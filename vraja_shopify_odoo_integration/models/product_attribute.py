from odoo import models


class ProductAttribute(models.Model):
    _inherit = "product.attribute"

    def get_attribute(self, attribute_string, attribute_type='radio', create_variant='always', auto_create=False):
        """
        Returns the attribute if it is available; otherwise, creates a new one and returns it.
        """
        attributes = self.search([('name', '=ilike', attribute_string),
                                  ('create_variant', '=', create_variant)], limit=1)
        if not attributes and auto_create:
            return self.create(({'name': attribute_string, 'create_variant': create_variant,
                                 'display_type': attribute_type}))
        return attributes
