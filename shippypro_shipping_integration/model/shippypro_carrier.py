# -*- coding: utf-8 -*-pack
from odoo import fields, models

class ShippyproCarrier(models.Model):
    _name = 'shippypro.carrier'

    name = fields.Char(string='Carrier Name')
    carrier_label = fields.Char(string='Carrier Label')
    carrier_id = fields.Char(string='Carrier Id')
    carrier_service = fields.Char(string='Carrier Service')


    def name_get(self):
        name_value =[]
        for record in self:
            new_value = '%s %s'%(record.carrier_id, record.carrier_label)
            name_value.append((record.id, new_value))
        return name_value
