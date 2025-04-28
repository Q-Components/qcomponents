from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        for order in self:
            if order.name == '/':
                order.name = self.env['ir.sequence'].next_by_code('sale.order') or 'New'
        return super(SaleOrder, self).action_confirm()
