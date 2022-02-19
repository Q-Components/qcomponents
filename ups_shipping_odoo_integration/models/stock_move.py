from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    # set the signature_required and insured_request field from stock move same as sale order date
    def _get_new_picking_values(self):
        vals = super(StockMove, self)._get_new_picking_values()
        if self.sale_line_id:
            vals['insured_amount'] = sum(
                [(line.price_unit * line.product_uom_qty) for line in self.sale_line_id.order_id.order_line if
                 not line.is_delivery])
        return vals
