from odoo import models, fields


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    ups_cod_amount = fields.Char("UPS COD Amount", help="UPS COD Price", readonly=True, copy=False)
    document_id = fields.Char("DocumentID", help="Forms History Document ID", readonly=True, copy=False)
    ups_paperless_invoice = fields.Boolean("UPS Paperless Invoice", help="True if you need to Ups Paperless Invoice")

    def generate_paperless_invoice(self):
        return self.carrier_id.ups_paperless_invoice_provider(self)
