# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError
import ipaddress

class BlockedIP(models.Model):
    _name = "website.blocked.ip"
    _description = "Blocked Website IP"
    _rec_name = 'ip_address'

    ip_address = fields.Char(string="Ip Address")
    active = fields.Boolean(default=True,string='Active')
    note = fields.Char('Note')

    @api.constrains('ip_address')
    def _check_ip(self):
        for rec in self:
            if self.search([('ip_address', '=', rec.ip_address), ('id', '!=', rec.id)], limit=1):
                raise ValidationError("This IP address is already blocked.")