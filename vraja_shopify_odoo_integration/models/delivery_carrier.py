import logging
from odoo import fields, models

_logger = logging.getLogger("Shopify")


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'
    _description = "Shopify Delivery Data"

    shopify_delivery_source = fields.Char(string="Shopify Delivery Source", copy=False,
                                          help="This fields value used for check shopify delivery source")
    shopify_delivery_code = fields.Char(string="Shopify Delivery Code", copy=False,
                                        help="This fields value used for check shopify delivery code")


    def shopify_search_generate_delivery_carrier(self, line, instance):
        """
        This method use to search and create delivery carrier base on received response in order line.
        @param : line : object of shipping line dictionary from order line response of shopify
                instance : object of instance
        @Return : object of carrier id
        """
        delivery_source = line.get('source')
        delivery_code = line.get('code')
        delivery_title = line.get('title')
        carrier = self.env['delivery.carrier']
        if delivery_source and delivery_code:
            carrier = self.search([("shopify_delivery_source", "=", delivery_source), ("shopify_delivery_code", "=", delivery_code)],limit=1)
            if not carrier:
                carrier = self.search([('name', '=', delivery_title)], limit=1)
                if carrier:
                    carrier.write({'shopify_delivery_source': delivery_source, 'shopify_delivery_code': delivery_code})

            if not carrier:
                carrier = self.create(
                    {'name': delivery_title, 'shopify_delivery_code': delivery_code, 'shopify_delivery_source': delivery_source,
                     'product_id': instance.shopify_shipping_product_id.id})
        return carrier
