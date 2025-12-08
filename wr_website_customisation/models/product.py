# -*- coding: utf-8 -*-
from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    x_studio_alternate_number = fields.Char(string="Alternate Number")

class ProductProduct(models.Model):
    _inherit = 'product.product'

    x_studio_alternate_number = fields.Char(string="Alternate Number")
