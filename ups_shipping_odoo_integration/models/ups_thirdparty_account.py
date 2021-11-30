# -*- coding: utf-8 -*-
from odoo import fields, models

class UPSThirdParty(models.Model):
    _name = 'ups.thirdparty.account'
    _rec_name = 'account_no'

    account_no = fields.Char(string='Account Number', required=True)
    zip = fields.Char(string='Zip code', required=True)
    country_id = fields.Many2one('res.country', string='Country', required=True)