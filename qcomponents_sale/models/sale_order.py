# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.onchange('partner_id', 'pricelist_id')
    def _onchange_partner(self):
        for order in self:
            for line in order.order_line:
                line._compute_discount()
                line._compute_amount()

    def _prepare_invoice(self):
        vals = super(SaleOrder,self)._prepare_invoice()

        pickings = self.picking_ids.filtered(
            lambda p: p.state == 'done' and p.carrier_tracking_ref
        )

        if pickings:
            vals['x_studio_tracking_reference'] = ', '.join(
                pickings.mapped('carrier_tracking_ref')
            )

        return vals
