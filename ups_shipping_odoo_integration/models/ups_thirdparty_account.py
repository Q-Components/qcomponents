# -*- coding: utf-8 -*-
from odoo import fields, models


class UPSThirdParty(models.Model):
    _name = 'ups.thirdparty.account'
    _description = "UPS Thirdparty Account"
    _rec_name = 'partner_id'

    partner_id = fields.Many2one('res.partner',string='Partner')
    account_no = fields.Char(string='Account Number')
    zip = fields.Char(string='Zip code')
    country_id = fields.Many2one('res.country', string='Country')