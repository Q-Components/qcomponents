from odoo import models, fields


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    is_gift_card_line = fields.Boolean(copy=False, default=False)
    shopify_order_line_id = fields.Char(string='Shopify Order Line ID')
    shopify_fulfillment_line_item_id = fields.Char(string='Shopify Fulfillment Line ID')
    shopify_fulfillment_order_id = fields.Char(string='Shopify Fulfilment Order ID')
    shopify_location_id = fields.Many2one('shopify.location',string='Shopify Location')
