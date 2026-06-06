from odoo import api, fields, models
from odoo.exceptions import ValidationError

class ChooseDeliveryCarrier(models.TransientModel):
    _inherit = "choose.delivery.carrier"

    delivery_method_margin = fields.Float(related="carrier_id.margin",string="Margin")
    insurance_fee = fields.Float(string="Insurance Fee")
    fuel_surcharge = fields.Float(string="Fuel Surcharge")
    remote_area_surcharge = fields.Float(string="Remote Area Surcharge")
    partner_discount = fields.Float(
        string="Partner Shipping Rate Discount",
        help="Shipping Rate Discount for this partner.",
    )

    @api.constrains('partner_discount')
    def check_partner_discount(self):
        for carrier in self:
            if carrier.partner_discount < 0 or carrier.partner_discount > 1:
                raise ValidationError("Partner Shipping Rate Discount must be between 0 and 100")


    @api.onchange('order_id')
    def _onchange_order_id_discount(self):
        if self.partner_id:
            self.partner_discount = self.partner_id.shipping_rate_discount

    def _get_delivery_rate(self):
        vals = super()._get_delivery_rate()
        if not vals.get('error_message'):
            base_price = self.delivery_price
            extra_fees = self.insurance_fee + self.fuel_surcharge + self.remote_area_surcharge
            total_amount = base_price + extra_fees
            discount_amount = total_amount * self.partner_discount
            self.delivery_price = total_amount - discount_amount
            self.display_price = total_amount - discount_amount
        return vals

    @api.onchange('insurance_fee', 'fuel_surcharge', 'remote_area_surcharge','partner_discount')
    def _onchange_surcharges(self):
        if not self.carrier_id:
            return
        vals = self._get_delivery_rate()
        if vals.get('error_message'):
            return {'error': vals['error_message']}


