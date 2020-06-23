from odoo import fields,models,api
from odoo.exceptions import ValidationError
import requests
import json
import logging
_logger = logging.getLogger("Bigcommerce")


class BigcommerceOrderShimpentStatus(models.Model):
    _inherit = 'stock.picking'

    bigcommerce_shimpment_id = fields.Char(string="Bigcommerce Shipment Numebr")

    def get_shipment_status(self):
        """
        This Method Used To Get Status Of Bigcommerce Order Status
        :return:  If Order Is Shipped return
        """

        sale_order_id = self.env['sale.order'].search([('id','=',self._context.get('active_id'))])
        bigcommerce_store_id = sale_order_id.warehouse_id.bigcommerce_store_ids
        bigcommerce_order_id = sale_order_id.big_commerce_order_id
        api_url ='%s%s/v2/orders/%s/shipments'%(bigcommerce_store_id.bigcommerce_api_url,bigcommerce_store_id.bigcommerce_store_hash,
                                                str(bigcommerce_order_id))
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'X-Auth-Client': '{}'.format(bigcommerce_store_id.bigcommerce_x_auth_client),
            'X-Auth-Token': "{}".format(bigcommerce_store_id.bigcommerce_x_auth_token)
        }
        try:
            response = requests.get(url=api_url,headers=headers)
            _logger.info("Sending Get Request To {}".format(response))
            if response.status_code in [200,201]:
                _logger.info("Get Successfully Response")
                response = response.json()
                traking_number =response.get('tracking_number')
                self.bigcommerce_shimpment_id = traking_number
                sale_order_id.bigcommerce_store_status = 'Shipped'

            elif response.status_code in [204]:
                sale_order_id.bigcommerce_shipment_order_status = 'Updating. . .'
            else:
                raise ValidationError("Getting Some Error {}".format(response.text))
        except Exception as e:
            raise ValidationError(e)

