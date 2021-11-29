from odoo import fields, models


class UPSStockPackage(models.Model):
    _inherit = 'stock.quant.package'

    ups_cod_parcel = fields.Boolean(string='UPS COD Package ?')
    ups_cod_amount = fields.Float(string='UPS Parcel COD Amount')
    custom_ups_tracking_number = fields.Char(string="UPS Tracking Number",
                                             help="If tracking number available print it in this field.")