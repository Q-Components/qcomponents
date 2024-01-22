# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

from odoo import models, fields

class StockMove(models.Model):
    _inherit = "stock.move"

    def _get_new_picking_values(self):
        """We need this method to set Shopify Instance in Stock Picking"""
        res = super(StockMove, self)._get_new_picking_values()
        order_id = self.sale_line_id.order_id
        if order_id.shopify_order_reference_id:
            res.update({'instance_id': order_id.instance_id.id, 'is_shopify_delivery_order': True})
        return res

class StockPicking(models.Model):
    """Inhetit the model to add the fields in this model related to connector"""
    _inherit = "stock.picking"

    updated_status_in_shopify = fields.Boolean(default=False)
    is_shopify_delivery_order = fields.Boolean("Shopify Delivery Order", default=False)
    instance_id = fields.Many2one("shopify.instance.integration", "Shopify Instance")
    shopify_fulfillment_id = fields.Char(string='Shopify Fulfillment Id')
    is_order_cancelled_in_shopify = fields.Boolean(string='Cancelled in Shopify?')
    is_shopify_error = fields.Boolean(string='Error/Exception in Shopify')

    def manually_update_shipment(self):
        self.env['sale.order'].update_order_status_in_shopify(self.instance_id, picking_ids=self)
        return True