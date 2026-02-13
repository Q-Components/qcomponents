# -*- coding: utf-8 -*-
from odoo import api, fields, models

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    is_product_location_updated = fields.Boolean(default=False,string="Product Location Updated with Quantity")