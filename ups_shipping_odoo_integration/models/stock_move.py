from odoo import models, fields, api

class StockMove(models.Model):
    _inherit = 'stock.move'

    remaining_qty = fields.Float(
        string="Remaining Qty",
        compute="_compute_remaining_qty",
        store=True
    )

    @api.depends('product_uom_qty', 'quantity')
    def _compute_remaining_qty(self):
        for move in self:
            done_qty = move.quantity
            move.remaining_qty = max(move.product_uom_qty - done_qty, 0.0)
