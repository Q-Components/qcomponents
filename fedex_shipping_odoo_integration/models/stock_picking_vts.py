from odoo.exceptions import ValidationError
from odoo import models, fields, api, _

class FedExPackageDetails(models.Model):
    _inherit = "stock.picking"

    def create_return_order(self):
        for picking in self:
            with_context = self._context.copy()
            with_context.update({'use_fedex_return': True})
            res = self.carrier_id.with_context(with_context).fedex_shipping_provider_send_shipping(picking)
            picking.write({'carrier_tracking_ref': res[0].get('tracking_number', ''),
                           'carrier_price': res[0].get('exact_price', 0.0)})
