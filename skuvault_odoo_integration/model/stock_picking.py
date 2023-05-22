from odoo import fields, models, _

class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    def forcefully_validate_picking(self):
        self._cr.execute("delete from stock_move_line where picking_id = %s"%self.id)
        for move_line in self.move_ids:
            move_line.quantity_done = move_line.product_uom_qty
        self._action_done()