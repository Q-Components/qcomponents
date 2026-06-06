from odoo import fields, models, api
from odoo.exceptions import ValidationError

class ResPartner(models.Model):
    _inherit = "res.partner"

    shipping_rate_discount = fields.Float(string="Shipping Rate Discount",help="Shipping Rate Discount for this partner")
    sale_order_discount = fields.Float(string="Sale Order Discount",help="Sale Order Discount for this partner")


    @api.constrains('sale_order_discount','shipping_rate_discount')
    def check_discount_constraints(self):
        for partner in self:
            if partner.sale_order_discount < 0 or partner.sale_order_discount > 1:
                raise ValidationError("Sale Order Discount must be between 0 and 100")
            if partner.shipping_rate_discount < 0 or partner.shipping_rate_discount > 1:
                raise ValidationError("Shipping Rate Discount must be between 0 and 100")



