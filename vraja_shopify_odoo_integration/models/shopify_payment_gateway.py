import json
import time
from datetime import datetime, timedelta
from odoo import models, fields
from .. import shopify
from ..shopify.pyactiveresource.connection import ClientError


class ShopifyPaymentGateway(models.Model):
    _name = 'shopify.payment.gateway'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Payment Gateway'

    name = fields.Char(string='Name', help='Enter Name', copy=False, tracking=True)
    code = fields.Char(string='Code', help='Enter Code', copy=False, tracking=True)
    instance_id = fields.Many2one('shopify.instance.integration', string='Instance', copy=False, tracking=True)
    company_id = fields.Many2one('res.company', string='Company', help='Select company', copy=False, tracking=True,
                                 default=lambda self: self.env.user.company_id)

    def import_payment_gateway(self, instance):
        """
        This method import payment gateway through Order API.
        """
        to_date = datetime.now()
        from_date = to_date - timedelta(7)
        log_id = self.env['shopify.log'].generate_shopify_logs('gateway', 'import', instance, 'Process Started')
        try:
            results = shopify.Order().find(status="any", updated_at_min=from_date,
                                           updated_at_max=to_date, fields=['gateway'], limit=250)
        except ClientError as error:
            if hasattr(error, "response"):
                if error.response.code == 429 and error.response.msg == "Too Many Requests":
                    time.sleep(int(float(error.response.headers.get('Retry-After', 5))))
                    results = shopify.Order().find(status="any", updated_at_min=from_date,
                                                   updated_at_max=to_date, fields=['gateway'], limit=250)
                else:
                    message = "Getting Some Error When Try To Import Gateway"
                    error = str(error.code) + "\n" + json.loads(error.response.body.decode()).get("errors")
                    self.env['shopify.log.line'].generate_shopify_process_line('gateway', 'import', instance,
                                                                               message, False, error, log_id, True)
        except Exception as error:
            message = "Getting Some Error When Try To Import Gateway"
            self.env['shopify.log.line'].generate_shopify_process_line('gateway', 'import', instance,
                                                                       message, False, error, log_id, True)

        for result in results:
            result = result.to_dict()
            gateway = result.get('gateway') or "no_payment_gateway"
            shopify_payment_gateway, existing_or_not = self.search_or_create_payment_gateway(instance, gateway)
            if existing_or_not:
                msg = "Gateway Already exist {}".format(shopify_payment_gateway and shopify_payment_gateway.name)
                self.env['shopify.log.line'].generate_shopify_process_line('gateway', 'import', instance, msg,
                                                                           False, result, log_id, False)
            else:
                msg = "Gateway Successfully Created {}".format(shopify_payment_gateway and shopify_payment_gateway.name)
                self.env['shopify.log.line'].generate_shopify_process_line('gateway', 'import', instance, msg,
                                                                           False, result, log_id, False)
        log_id.shopify_operation_message = 'Process Has Been Finished'
        if not log_id.shopify_operation_line_ids:
            log_id.unlink()
        return True

    def search_or_create_payment_gateway(self, instance, gateway_name):
        """
        This method searches for payment gateway and create it, if not found.
        """
        shopify_payment_gateway = self.search([('code', '=', gateway_name),
                                               ('instance_id', '=', instance.id)], limit=1)
        existing_or_not = True
        if not shopify_payment_gateway:
            shopify_payment_gateway = self.create({'name': gateway_name,
                                                   'code': gateway_name,
                                                   'instance_id': instance.id,
                                                   'company_id': instance.company_id.id})
            existing_or_not = False

        return shopify_payment_gateway, existing_or_not
