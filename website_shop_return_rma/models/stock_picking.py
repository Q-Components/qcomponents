# -*- coding: utf-8 -*-

from odoo import models, fields, api


class StockPicking(models.Model):
    _inherit = "stock.picking"
    
    rma_order_id = fields.Many2one(
       'return.order',
       string ="RMA Order",
   )