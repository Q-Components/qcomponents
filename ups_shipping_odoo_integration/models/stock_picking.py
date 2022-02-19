from odoo import fields, models, api, _


class StockPicking(models.Model):
    _inherit = 'stock.picking'
    ups_cod_bulk_value = fields.Float(string='UPS Bulk Shipment COD Value', compute='_compute_ups_bulk_value', store=True)
    insured_amount = fields.Float(string="UPS Insured Amount",
                                  help="Use this Insured Request, It's affected on rate.")

    def create_ups_label(self):
        if self.delivery_type == "ups_shipping_provider":
            res = self.carrier_id.ups_shipping_provider_send_shipping(self)
            self.write({'carrier_tracking_ref': res[0].get('tracking_number', ''),
                        'carrier_price': res[0].get('exact_price', 0.0)})

    def put_in_pack(self):
        res = super(StockPicking, self).put_in_pack()
        cod_value = 0.0
        if self.carrier_id and self.carrier_id.ups_cod_parcel:
           for move_line in self.move_line_ids:
               if not move_line.result_package_id:
                    cod_value += move_line.qty_done * move_line.move_id.sale_line_id.price_unit
           res.get('context').update({'default_ups_cod_parcel': 'True'})
           res.get('context').update({'default_ups_cod_amount': cod_value})
           return res
        else:
            return res

    @api.depends('move_line_ids', 'move_line_ids.product_uom_id', 'move_line_ids.qty_done', 'move_line_ids.move_id.sale_line_id.price_unit')
    def _compute_ups_bulk_value(self):
        value = 0.0
        for picking in self:
            for move_line in picking.move_line_ids:
                if move_line.product_id and not move_line.result_package_id:
                    value += move_line.qty_done * move_line.move_id.sale_line_id.price_unit
            picking.ups_cod_bulk_value = value
            # self.ups_cod_bulk_value = sum(price) or 0.0