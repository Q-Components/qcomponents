import binascii

from odoo import fields, models, _, api
import requests
import json
import logging

_logger = logging.getLogger(__name__)
from odoo.exceptions import ValidationError
from requests.auth import HTTPBasicAuth

class ResCompany(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(selection_add=[("shippypro", "Shippypro")], ondelete={'shippypro': 'set default'})

    shippypro_shipping_service = fields.Selection([('express', 'Express'), ('Standard', 'standard')],
                                                  string="Shippypro Shipping Service")
    shippypro_payment_method = fields.Selection([('Paypal', 'Paypal'), ('COD', 'COD')],
                                                string="Shippypro Payment Method")
    shippypro_package_id = fields.Many2one('stock.package.type', string="Default Package")
    shippypro_carrier_id = fields.Many2one('shippypro.carrier', string='Shippypro Carrie')

    def shippypro_rate_shipment(self, order):
        request_data = self.shippypro_rate_request_data(order)
        url = self.company_id and self.company_id.shippypro_api_url
        headers = {
            'Content-Type': 'application/json'
        }
        username = self.company_id and self.company_id.shippypro_api_key
        try:
            _logger.info(">>> sending data to {0} \n request data:- {1}".format(url, request_data))
            response_data = requests.post(url=url,auth=HTTPBasicAuth(username=username, password=""), data=request_data, headers=headers)
            shippypro_service_rate_obj = self.env['shippypro.service.rate']
            if response_data.status_code in [200, 201]:
                _logger.info(">>> get successfully response from SHIP RATE API")
                response_data = response_data.json()
                rates = response_data.get('Rates')
                if not rates:
                    raise ValidationError(_('Rate not found in response \n {}'.format(response_data)))
                existing_record = shippypro_service_rate_obj.sudo().search([('sale_id', '=', order.id)])
                existing_record.unlink()
                for rate in rates:
                    vals = {
                        'carrier_name': rate.get('carrier'),
                        'carrier_id': rate.get('carrier_id'),
                        'carrier_label': rate.get('carrier_label'),
                        'carrier_rate': float(rate.get('rate')),
                        'carrier_rate_id': rate.get('rate_id'),
                        'delivery_day': rate.get('delivery_days'),
                        'service': rate.get('service'),
                        'sale_id': order.id,
                        'order_id': rate.get('order_id')
                    }
                    shippypro_service_rate_obj.sudo().create(vals)
                shippypro_service_id = self.env['shippypro.service.rate'].sudo().search([('sale_id', '=', order.id)],
                                                                                        order='carrier_rate', limit=1)
                order.shippypro_service_id = shippypro_service_id and shippypro_service_id.id
                return {'success': True, 'price': shippypro_service_id and shippypro_service_id.carrier_rate or 0.0,
                        'error_message': False, 'warning_message': False}
            else:
                raise ValidationError(response_data.content)
        except Exception as error:
            raise ValidationError(error)

    def shippypro_rate_request_data(self, order):
        """
        :returns this method return request data of rate api
        """
        receiver_id = order and order.partner_id
        sender_id = order and order.company_id

        request_data = {
            "Method": "GetRates",
            "Params": {
                "to_address": {
                    "name": receiver_id.name,
                    "company": receiver_id.name,
                    "street1": receiver_id.street,
                    "street2": receiver_id.street2 or " ",
                    "city": receiver_id.city,
                    "state": receiver_id and receiver_id.state_id and receiver_id.state_id.code or " ",
                    "zip": receiver_id.zip,
                    "country": receiver_id and receiver_id.country_id and receiver_id.country_id.code or " ",
                    "phone": receiver_id.phone or " ",
                    "email": receiver_id.email or " "
                },
                "from_address": {
                    "name": sender_id.name,
                    "company": sender_id.name,
                    "street1": sender_id.street,
                    "street2": sender_id.street2 or " ",
                    "city": sender_id.city,
                    "state": sender_id and sender_id.state_id and sender_id.state_id.code or " ",
                    "zip": sender_id.zip,
                    "country": sender_id and sender_id.country_id and sender_id.country_id.code or " ",
                    "phone": sender_id.phone or " ",
                    "email": sender_id.email or " ",
                },
                "parcels": [
                    {
                        "length": self.shippypro_package_id.packaging_length,
                        "width": self.shippypro_package_id.width,
                        "height": self.shippypro_package_id.height,
                        "weight": sum([i.product_id.weight * i.product_uom_qty for i in
                                       order.order_line.filtered(lambda order_line: order_line.is_delivery == False)])               
                    }
                ],
                "Insurance": 0,
                "InsuranceCurrency": self.company_id.currency_id.name,
                "CashOnDelivery": 0,
                "CashOnDeliveryCurrency": self.company_id and self.company_id.currency_id and self.company_id.currency_id.name,
                "ContentDescription": "Shoes",
                "TotalValue": "%s %s" % (order.amount_total, self.company_id.currency_id.name),
                "ShippingService": "{}".format(self.shippypro_shipping_service)
            }
        }
        return json.dumps(request_data)

    def shippypro_ship_api_request_data(self, pickings):
        """
        :returns this method return request data for ship api
        """

        sender_id = self.company_id
        receiver_id = pickings.partner_id
        parcel = []
        shippypro_service_id = pickings.sale_id and pickings.sale_id.shippypro_service_id
        carrier_name = shippypro_service_id and shippypro_service_id.carrier_name or \
                       self.shippypro_carrier_id and self.shippypro_carrier_id.name
        carrier_service = shippypro_service_id and shippypro_service_id.service or \
                          self.shippypro_carrier_id and self.shippypro_carrier_id.carrier_service
        carrier_id = shippypro_service_id and shippypro_service_id.carrier_id or self.shippypro_carrier_id and self.shippypro_carrier_id.carrier_id
        if pickings.package_ids:
            for package in pickings.package_ids:
                parcel_dimension = {
                    "length": package.package_type_id.packaging_length or 0,
                    "width": package.package_type_id.width or 0,
                    "height": package.package_type_id.height or 0,
                    "weight": package.shipping_weight or 0
                }
                parcel.append(parcel_dimension)
        if pickings.weight_bulk:
            parcel.append({
                "length": self.shippypro_package_id.packaging_length or 0,
                "width": self.shippypro_package_id.width or 0,
                "height": self.shippypro_package_id.height or 0,
                "weight": pickings.weight_bulk or 0
            })
        request_data = {
            "Method": "Ship",
            "Params": {
                "to_address": {
                    "name": receiver_id.name,
                    "company": receiver_id.name,
                    "street1": receiver_id.street,
                    "street2": receiver_id.street2 or " ",
                    "city": receiver_id.city or " ",
                    "state": receiver_id.state_id and receiver_id.state_id.code or " ",
                    "zip": receiver_id.zip,
                    "country": receiver_id.country_id and receiver_id.country_id.code or " ",
                    "phone": receiver_id.phone or " ",
                    "email": receiver_id.email or " "
                },
                "from_address": {
                    "name": sender_id.name,
                    "company": sender_id.name,
                    "street1": sender_id.street,
                    "street2": sender_id.street2 or " ",
                    "city": sender_id.city,
                    "state": sender_id and sender_id.state_id and sender_id.state_id.code or " ",
                    "zip": sender_id.zip,
                    "country": sender_id and sender_id.country_id and sender_id.country_id.code or " ",
                    "phone": sender_id.phone or " ",
                    "email": sender_id.email or " "
                },
                "parcels": parcel,
                "TotalValue": "%s %s" % (pickings.sale_id.amount_total, self.company_id.currency_id.name),
                "TransactionID": pickings.sale_id.name,
                "ContentDescription": "{}".format(pickings.note),
                "Insurance": 0,
                "InsuranceCurrency": self.company_id and self.company_id.currency_id and self.company_id.currency_id.name,
                "CashOnDelivery": 0,
                "CashOnDeliveryCurrency": self.company_id and self.company_id.currency_id and self.company_id.currency_id.name,
                "CashOnDeliveryType": 0,
                "CarrierName": carrier_name,
                "CarrierService": carrier_service,
                "CarrierID": int(carrier_id),
                "OrderID": shippypro_service_id.order_id or " ",
                "RateID": shippypro_service_id.carrier_rate_id or " ",
                "Incoterm": "DAP",
                "BillAccountNumber": "",
                "PaymentMethod": self.shippypro_payment_method,
                "Note": "{}".format(pickings.note),
            }
        }
        return json.dumps(request_data)

    @api.model
    def shippypro_send_shipping(self, pickings):
        request_data = self.shippypro_ship_api_request_data(pickings)
        headers = {
            'Content-Type': 'application/json'
        }
        username = self.company_id and self.company_id.shippypro_api_key
        try:
            response_data = requests.post(url=self.company_id and self.company_id.shippypro_api_url,
                                          auth=HTTPBasicAuth(username=username, password=""),
                                          headers=headers,
                                          data=request_data)
            if response_data.status_code in [200, 201]:
                response_data = response_data.json()
                order_id = response_data.get('NewOrderID')
                pickings.shippypro_order_id = order_id
                if not order_id:
                    raise ValidationError(_('order id not found in response {}').format(response_data))
                order_data = self.generate_label_using_order_id(order_id)
                label_data = order_data.get('PDF')
                for data in label_data:
                    data = binascii.a2b_base64(str(data))
                    message = ((
                                   "Label created!<br/> <b>Order  Number : </b>%s<br/>") % (
                                   order_id,))
                    pickings.message_post(body=message, attachments=[
                        ('Shippypro-%s.%s' % (order_id, "pdf"), data)])
                tracking_number = order_data.get('TrackingNumber')
                tracking_url = order_data.get('TrackingExternalLink')
                pickings.shippypro_tracking_url = tracking_url
                shipping_data = {
                    'exact_price': float(0.0),
                    'tracking_number': tracking_number}
                shipping_data = [shipping_data]
                return shipping_data
            else:
                raise ValidationError(_(response_data.content))
        except Exception as error:
            raise ValidationError(_(error))

    def generate_label_using_order_id(self, order_id):
        request_data = {
            "Method": "GetLabelUrl",
            "Params": {
                "OrderID": int(order_id),
                "LabelType": "PDF"
            }
        }
        headers = {
            'Content-Type': 'application/json'
        }
        username = self.company_id and self.company_id.shippypro_api_key
        try:
            response_data = requests.post(url=self.company_id and self.company_id.shippypro_api_url, headers=headers,
                                          auth=HTTPBasicAuth(username=username, password=""),
                                          data=json.dumps(request_data))
            if response_data.status_code in [200, 201]:
                _logger.info(">>> get successfully label data")
                response_data = response_data.json()
                return response_data
            else:
                raise ValidationError(response_data)
        except Exception as error:
            raise ValidationError(error)

    def shippypro_cancel_shipment(self, picking):
        data = {
            "Method": "ArchiveOrders",
            "Params": {
                "OrderIDS": [
                    int(picking.shippypro_order_id)
                ]
            }
        }
        headers = {
            'Content-Type': 'application/json'
        }
        username = self.company_id and self.company_id.shippypro_api_key
        try:
            _logger.info("Sending data for cancel the order {}".format(data))
            response_data = requests.post(url=self.company_id and self.company_id.shippypro_api_url, headers=headers,
                                          auth=HTTPBasicAuth(username=username, password=""),
                                          data=json.dumps(data))
            if response_data.status_code in [200, 201]:
                _logger.info("Get successfully response of cancel api")
                response_data = response_data.json()
                result = response_data and response_data.get('Result')
                if result in ["OK", "ok"]:
                    _logger.info("Successfully cancel order {}".format(picking.shippypro_order_id))
                else:
                    raise ValidationError("get some error to cancel the  order \n".format(response_data))
            else:
                raise ValidationError("get some error to cancel the  order \n {}".format(response_data.text))
        except Exception as error:
            raise ValidationError(_(error))

    def shippypro_get_tracking_link(self, pickings):
        if pickings.shippypro_tracking_url:
            return pickings.shippypro_tracking_url

