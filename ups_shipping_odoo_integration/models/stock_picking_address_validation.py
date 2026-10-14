from odoo import fields, models

# UPS Address Validation (XAV) only supports the US and Puerto Rico.
UPS_AV_COUNTRIES = ('US', 'PR')


class StockPickingUpsAddressValidation(models.Model):
    _inherit = "stock.picking"

    ups_av_checked = fields.Boolean(string="UPS Address Checked", copy=False)

    def write(self, vals):
        if 'partner_id' in vals and 'ups_av_checked' not in vals:
            vals = dict(vals, ups_av_checked=False)   # address changed: check again
        return super().write(vals)

    def _ups_needs_av(self):
        self.ensure_one()
        carrier = self.carrier_id
        return bool(
            self.picking_type_code == 'outgoing'
            and self.state not in ('done', 'cancel')
            and not self.ups_av_checked
            and not self.carrier_tracking_ref
            and self.partner_id
            and self.partner_id.country_id.code in UPS_AV_COUNTRIES
            # a UPS Access Point address is already validated by UPS
            and not (self.sale_id and self.sale_id.ups_shipping_location_id)
            and carrier
            and carrier.delivery_type == 'ups_provider'
            and carrier.ups_validate_address
        )

    def button_validate(self):
        # Context key ups_av_skip lets automated callers bypass the check.
        if not self.env.context.get('ups_av_skip'):
            for picking in self:
                if not picking._ups_needs_av():
                    continue
                carrier = picking.carrier_id
                res = carrier.ups_validate_partner_address(picking.partner_id)

                if res['status'] in ('review', 'invalid', 'error'):
                    # Stop here: the wizard shows the suggestions or the UPS error and
                    # the user chooses; it then resumes validation and shipment creation.
                    return self.env['ups.address.wizard'].open_from_result(picking, res)

                if (res['status'] == 'minor' and carrier.ups_auto_correct_address
                        and res.get('suggested')):
                    carrier._ups_apply_suggested_address(
                        picking.partner_id, res['suggested'])

                if res['status'] != 'error':
                    picking.ups_av_checked = True   # don't check again
        return super().button_validate()
