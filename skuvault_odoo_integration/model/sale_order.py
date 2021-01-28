# -*- coding: utf-8 -*-
from odoo import fields, models, _
import logging
import requests
import json
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger("Skuvault")


class SkuvaultSaleOrder(models.Model):
    _inherit = 'sale.order'

    skuvault_order_id = fields.Char(string="Skuvault Order Id", help="Order Id of Skuvault Order")

    def check_required_values(self):
        """
        :returns True
        :raises to check whatever field
        """
        if not self.warehouse_id:
            raise ValidationError(_('please select warehouse'))
        if not self.warehouse_id.skuvault_tenantToken and self.warehouse_id.skuvault_UserToken:
            raise UserError(_('please generate tenant and user token'))
        if not self.partner_id:
            raise ValidationError(_('please select the customer'))
        for order in self.order_line:
            if not order.product_id.default_code:
                raise ValidationError(
                    _('please define sku code in {}').format(order.product_id and order.product_id.name))
        return True

    def order_list(self):
        """
        :return list of order line
        """
        order_list = []
        for order in self.order_line:
            data = {
                "Quantity": int(order.product_uom_qty),
                "Sku": "{}".format(order.product_id and order.product_id.default_code),
                "UnitPrice": order.price_subtotal
            }
            order_list.append(data)
        return order_list

    def export_order_request_data(self):
        """
        :return request data of skuvault export order api
        """
        data_dict = {
            "ItemSkus": self.order_list(),
            "Notes": self.note or " ",
            "OrderId": self.name,
            "ShippingInfo": {
                "City": self.partner_id and self.partner_id.city or " ",
                "Country": self.partner_id and self.partner_id.country_id and self.partner_id.country_id.name or " ",
                "Email": self.partner_id.email or " ",
                "FirstName": self.partner_id and self.partner_id.name,
                "Line1": self.partner_id and self.partner_id.street,
                "Line2": self.partner_id and self.partner_id.street2 or " ",
                "PhoneNumber": self.partner_id and self.partner_id.phone or " ",
                "Postal": self.partner_id and self.partner_id.zip or " ",
                "Region": self.partner_id and self.partner_id.state_id and self.partner_id.state_id.name or " ",
            },
            "TenantToken": "{}".format(self.warehouse_id and self.warehouse_id.skuvault_tenantToken),
            "UserToken": "{}".format(self.warehouse_id and self.warehouse_id.skuvault_UserToken)
        }
        return data_dict

    def export_order_to_skuvault(self):
        """
        :return export order to skuvault and save order id in odoo
        """
        self.check_required_values()
        request_data = self.export_order_request_data()
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        url = "{}/api/sales/syncOnlineSale".format(self.warehouse_id and self.warehouse_id.skuvault_api_url)
        _logger.info(">> sending post request to {}".format(url))
        _logger.info(">>> request data : {}".format(request_data))
        try:
            response_data = requests.post(url=url, headers=headers, data=json.dumps(request_data))
        except Exception as error:
            raise ValidationError(_('Getting some error in api calling \n {}').format(error))
        if response_data.status_code in [200, 201]:
            _logger.info(":: get successfully response from {}".format(url))
            response_data = response_data.json()
            status = response_data.get('Status')
            order_id = response_data.get('OrderId')
            if status == "OK":
                _logger.info("Successfully export the order")
                self.message_post(body=_('Order Exported to Skuvault %s' % (order_id)))
                self.skuvault_order_id = order_id
                return {
                    'effect': {
                        'fadeout': 'slow',
                        'message': "Yeah! Successfully Export Order in Skuvault .",
                        'img_url': '/web/static/src/img/smile.svg',
                        'type': 'rainbow_man',
                    }
                }
            else:
                raise ValidationError(_('error to export order \n {}').format(response_data))
        else:
            raise ValidationError(
                _('getting some error from {0} \n response data : {1}').format(url, response_data.text))
