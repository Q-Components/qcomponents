# -*- coding: utf-8 -*-
from odoo import models, fields

class Website(models.Model):
    _inherit = 'website'

    product_search_field_ids = fields.Many2many('ir.model.fields',string='Product Search Fields')