from odoo import fields, models

# FedEx address validation is reliable mainly for these countries.
FEDEX_AV_COUNTRIES = ('US', 'CA')


class StockPickingFedexAddressValidation(models.Model):
    _inherit = "stock.picking"

    fedex_av_checked = fields.Boolean(string="FedEx Address Checked", copy=False)

    def write(self, vals):
        if 'partner_id' in vals and 'fedex_av_checked' not in vals:
            vals = dict(vals, fedex_av_checked=False)   # address changed: check again
        return super().write(vals)

    def _fedex_needs_av(self):
        self.ensure_one()
        carrier = self.carrier_id
        return bool(
            self.picking_type_code == 'outgoing'
            and self.state not in ('done', 'cancel')
            and not self.fedex_av_checked
            and not self.carrier_tracking_ref
            and self.partner_id
            and self.partner_id.country_id.code in FEDEX_AV_COUNTRIES
            and carrier
            and carrier.delivery_type == 'fedex_shipping_provider'
            and carrier.fedex_validate_address
        )

    def button_validate(self):
        # Context key fedex_av_skip lets automated callers bypass the check.
        if not self.env.context.get('fedex_av_skip'):
            for picking in self:
                if not picking._fedex_needs_av():
                    continue
                carrier = picking.carrier_id
                res = carrier.fedex_validate_partner_address(
                    picking.partner_id, ref=picking.name)

                if res['status'] in ('review', 'invalid'):
                    # Stop here: the user chooses an address in the wizard,
                    # the wizard then resumes this validation (and shipment).
                    return self.env['fedex.address.wizard'].open_from_result(picking, res)

                if (res['status'] == 'minor' and carrier.fedex_auto_correct_address
                        and res.get('suggested')):
                    carrier._fedex_apply_suggested_address(
                        picking.partner_id, res['suggested'])

                if res['status'] != 'error':
                    picking.fedex_av_checked = True   # don't check again
        return super().button_validate()
