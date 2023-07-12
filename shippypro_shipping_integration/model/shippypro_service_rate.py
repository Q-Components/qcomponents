from odoo import fields, models, api


class ShippyproServiceRate(models.Model):
    _name = 'shippypro.service.rate'
    _rec_name = 'service'
    carrier_name = fields.Char(string="Carrier")
    carrier_id = fields.Char(string="Carrier Id")
    carrier_label = fields.Char(string="Carrier Label")
    carrier_rate = fields.Float(string="Rate")
    carrier_rate_id = fields.Char(string="Rate Id")
    delivery_day = fields.Char(string="Delivery Days")
    service = fields.Char(string="Service")
    order_id = fields.Char(string="Order Id")

    sale_id = fields.Many2one('sale.order')

    def set_service(self):
        self.ensure_one()
        carrier = self.sale_id.carrier_id
        self.sale_id.shippypro_service_id = self.id
        self.sudo().sale_id.sudo().carrier_id = carrier.id
        self.sudo().sale_id.sudo().set_delivery_line(carrier,self.carrier_rate)

