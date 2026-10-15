from odoo import models, fields


class StockMove(models.Model):
    _inherit = "stock.move"

    def _get_new_picking_values(self):
        res = super(StockMove, self)._get_new_picking_values()
        order_id = self.sale_line_id.order_id

        if order_id:
            # Filter lines for physical, non-delivery products in this specific sale order
            eligible_lines = order_id.order_line.filtered(
                lambda l: l.product_id.type not in ('service', 'digital') and not l.is_delivery
            )
            insurance_amount = round(sum(eligible_lines.mapped('price_subtotal')), 2)
            res.update({'fedex_insurance_amount': insurance_amount})

        return res