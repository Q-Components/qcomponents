from odoo import fields, models
from odoo.addons.delivery.wizard.choose_delivery_package import ChooseDeliveryPackage
from odoo.tools.float_utils import float_compare


def put_in_pack(self):
    picking_move_lines = self.picking_id.move_line_ids
    if not self.picking_id.picking_type_id.show_reserved:
        picking_move_lines = self.picking_id.move_line_nosuggest_ids

    move_line_ids = picking_move_lines.filtered(lambda ml:
                                                float_compare(ml.qty_done, 0.0,
                                                              precision_rounding=ml.product_uom_id.rounding) > 0
                                                and not ml.result_package_id
                                                )
    if not move_line_ids:
        move_line_ids = picking_move_lines.filtered(lambda ml: float_compare(ml.product_uom_qty, 0.0,
                                                                             precision_rounding=ml.product_uom_id.rounding) > 0 and float_compare(
            ml.qty_done, 0.0,
            precision_rounding=ml.product_uom_id.rounding) == 0)

    delivery_package = self.picking_id._put_in_pack(move_line_ids)
    # write shipping weight and product_packaging on 'stock_quant_package' if needed
    if self.delivery_packaging_id:
        delivery_package.packaging_id = self.delivery_packaging_id
        if self.shipping_weight:
            delivery_package.shipping_weight = self.shipping_weight
        if self.ups_cod_parcel:
            delivery_package.ups_cod_parcel = self.ups_cod_parcel
        if self.ups_cod_amount:
            delivery_package.ups_cod_amount = self.ups_cod_amount




ChooseDeliveryPackage.put_in_pack = put_in_pack


class ChooseDeliveryPackage(models.TransientModel):
    _inherit = 'choose.delivery.package'

    ups_cod_parcel = fields.Boolean(string='UPS COD Package ?')
    ups_cod_amount = fields.Float(string='UPS Parcel COD Amount')
