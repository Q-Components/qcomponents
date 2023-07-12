from odoo import fields, models, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    shippypro_service_ids = fields.One2many('shippypro.service.rate', 'sale_id', string="Shippypro Service rate")
    shippypro_service_id = fields.Many2one('shippypro.service.rate', string="Shippypro Service Method")

