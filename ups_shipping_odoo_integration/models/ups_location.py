from odoo import models,api,fields

class UpsLocation(models.Model):
    _name = "ups.location"
    _rec_name = "name"
    name = fields.Char(string="Location Name", help="Location Name")
    location_id = fields.Char(string="Location Id", help="Location Id")
    street = fields.Char(string="Street", help="Ups Street")
    street2 = fields.Char(string="Area", help="UPS Area")
    city = fields.Char(string="City", help="UPS City")
    state_code = fields.Char(string="State", help="UPS State")
    zip = fields.Char(string="Zip", help="UPS Zip")
    country_code = fields.Char(string="Country Code", help="UPS Country Code")
    ups_sale_order_id = fields.Many2one("sale.order",string="Sale Order")

    def set_location(self):
        self.ensure_one()
        self.ups_sale_order_id.ups_shipping_location_id = self.id
