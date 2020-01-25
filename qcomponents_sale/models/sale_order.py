# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.onchange('partner_id', 'pricelist_id')
    def _onchange_partner(self):
        for order in self:
            for line in order.order_line:
                line._onchange_discount()
                line.product_id_change()
