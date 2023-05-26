from odoo.addons.delivery.models.stock_move import StockMove


def _get_new_picking_values(self):
    vals = super(StockMove, self)._get_new_picking_values()
    vals['carrier_id'] = self.group_id.sale_id.carrier_id.id
    vals['x_studio_field_erYmc'] = self.group_id.sale_id.payment_term_id.id
    return vals


StockMove._get_new_picking_values = _get_new_picking_values
