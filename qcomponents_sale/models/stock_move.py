from odoo.addons.stock_delivery.models.stock_move import StockMove


# def _get_new_picking_values(self):
#     vals = super(StockMove, self)._get_new_picking_values()
#     vals['carrier_id'] = self.group_id.sale_id.carrier_id.id
#     vals['x_studio_field_erYmc'] = self.group_id.sale_id.payment_term_id.id
#     return vals

def _get_new_picking_values(self):
    vals = super(StockMove, self)._get_new_picking_values()
    carrier_id = self.reference_ids.sale_ids.carrier_id.id

    x_studio_field_erYmc = self.reference_ids.sale_ids.payment_term_id.id

    carrier_tracking_ref = False
    if self.move_orig_ids.picking_id.carrier_id:
        # check if previous picking have carrier_id take carrier from that
        # earlier we were taking carrier from sale but since carrier can be changed  or updated in next steps so now we take carrier from prev picking
        carrier_id = self.move_orig_ids.picking_id.carrier_id.id
        carrier_tracking_ref = self.move_orig_ids.picking_id.carrier_tracking_ref
    # propagating carrier and tracking ref only if carrier propagation rule allow
    if any(rule.propagate_carrier for rule in self.rule_id):
        vals['carrier_tracking_ref'] = carrier_tracking_ref
        vals['carrier_id'] = carrier_id
        vals['x_studio_field_erYmc'] = x_studio_field_erYmc
    return vals


StockMove._get_new_picking_values = _get_new_picking_values
