# -*- coding: utf-8 -*-

from odoo import models, fields, api

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    
    return_rma_ids = fields.Many2many(
        'return.order',
        string="Return RMA",
    )
    return_quantity = fields.Float(
        string="Return Quantity",
    )

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
