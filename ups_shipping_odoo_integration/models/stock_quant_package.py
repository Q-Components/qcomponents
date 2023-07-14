from odoo import fields, models


class UPSStockPackage(models.Model):
    _inherit = 'stock.quant.package'

    ups_cod_parcel = fields.Boolean(string='UPS COD Package ?')
    ups_cod_amount = fields.Float(string='UPS Parcel COD Amount')
    custom_ups_tracking_number = fields.Char(string="UPS Tracking Number",
                                             help="If tracking number available print it in this field.")

    def create(self, vals):
        res = super(UPSStockPackage, self).create(vals)
        picking_record = self.env['stock.picking'].browse(self._context.get('default_picking_id'))
        if picking_record and picking_record.delivery_type == 'ups_shipping_provider' and picking_record.carrier_id:
            res.ups_cod_parcel = picking_record.carrier_id.ups_cod_parcel
        return res
