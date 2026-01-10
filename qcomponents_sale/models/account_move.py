# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

class Accountmove(models.Model):
    _inherit = "account.move"

    carrier_tracking_reference = fields.Char(string="Tracking Reference")


