from odoo import models


class ProductAttributeValue(models.Model):
    _inherit = "product.attribute.value"

    def get_attribute_values(self, name, attribute_id, auto_create=False):
        """
        Returns the attribute value if it is found; otherwise, creates a new one and returns it.
        """
        attribute_values = self.search([('name', '=', name), ('attribute_id', '=', attribute_id)], limit=1)
        if not attribute_values:
            attribute_values = self.search([('name', '=ilike', name), ('attribute_id', '=', attribute_id)], limit=1)
        if not attribute_values and auto_create:
            return self.create(({'name': name, 'attribute_id': attribute_id}))
        return attribute_values
