import base64
import logging
import time

from odoo import http
from odoo.http import request
from datetime import datetime, timedelta

_logger = logging.getLogger("Shopify Controller")


class MarketplaceProductImage(http.Controller):

    @http.route(['/shopify/product/image/<string:encodedimage>'], type='http', auth='public')
    def retrive_shopify_product_image_from_url(self, encodedimage=''):
        if encodedimage:
            try:
                decode_data = base64.urlsafe_b64decode(encodedimage)
                res_id = str(decode_data, "utf-8")
                status, headers, content = request.env['ir.http'].sudo().binary_content(
                    model='shopify.product.image', id=res_id,
                    field='image')
                content_base64 = base64.b64decode(content) if content else ''
                headers.append(('Content-Length', len(content_base64)))
                return request.make_response(content_base64, headers)
            except Exception:
                return request.not_found()
        return request.not_found()


class Main(http.Controller):

    @http.route(['/shopify_odoo_webhook_for_customer_create'], csrf=False,
                auth="public", type="json")
    def customer_create_webhook(self):
        """
        Route for handling customer create webhook for Shopify. This route calls while new customer create
        in the Shopify store.
        """
        webhook_route = request.httprequest.path.split('/')[1]
        # 1) Create Customer (shopify_odoo_webhook_for_customer_create)

        res, instance = self.get_basic_info(webhook_route)
        if not res:
            return
        if res.get("first_name") and res.get("last_name"):
            _logger.info("%s call for Customer: %s", webhook_route,
                         (res.get("first_name") + " " + res.get("last_name")))
            self.customer_webhook_process(instance)
        return

    def customer_webhook_process(self, instance):
        """
        This method used for call child method of customer create process.
        """
        time.sleep(10)
        to_date = datetime.now()
        from_date = to_date - timedelta(days=10)
        create_customer_queue = request.env["customer.data.queue"].sudo()
        create_customer_queue.import_customers_from_shopify_to_odoo(instance, from_date, to_date)
        return True

    @http.route("/shopify_odoo_webhook_for_orders_create", csrf=False, auth="public", type="json")
    def order_create_webhook(self):
        """
        Route for handling the order create webhook of Shopify. This route calls while new order create
        in the Shopify store.
        """
        res, instance = self.get_basic_info("shopify_odoo_webhook_for_orders_create")
        order_data_queue = request.env['order.data.queue']
        if not res:
            return

        _logger.info("CREATE ORDER WEBHOOK call for order: %s", res.get("name"))

        fulfillment_status = res.get("fulfillment_status") or "unfulfilled"
        if fulfillment_status in ["fulfilled", "unfulfilled", "partial"]:
            res["fulfillment_status"] = fulfillment_status
            order_data_queue.sudo().order_webhook_process(instance, res)
        return

    def order_webhook_process(self, instance_id, res):
        _logger.info("shopify order response :: {".format(res))
        queue_id = request.env['order.data.queue'].generate_shopify_order_queue(instance_id)
        request.env['order.data.queue.line'].create_shopify_order_queue_line(res, instance_id,
                                                                             queue_id)
        
    def get_basic_info(self, route):
        """
        This method is used to check that instance and webhook are active or not. If yes then return response and
        instance, If no then return response as False and instance.
        """
        res = request.get_json_data()
        _logger.info("Get json data : ", res)
        host = request.httprequest.headers.get("X-Shopify-Shop-Domain")
        instance = request.env["shopify.instance.integration"].sudo().with_context(active_test=False).search(
            [("shopify_url", "ilike", host)], limit=1)
        webhook = request.env["shopify.webhook"].sudo().search([("delivery_url", "ilike", route),
                                                                ("instance_id", "=", instance.id)], limit=1)

        if not instance.active or not webhook.state == "active":
            _logger.info("The method is skipped. It appears the instance:%s is not active or that "
                         "the webhook %s is not active.", instance.name, webhook.webhook_name)
            res = False
        return res, instance
