import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from .. import shopify

_logger = logging.getLogger("Shopify Webhook")


class ShopifyWebhook(models.Model):
    _name = "shopify.webhook"
    _description = 'Shopify Webhook'

    webhook_name = fields.Char(string='Name')
    state = fields.Selection([('active', 'Active'), ('inactive', 'Inactive')], default='inactive')
    webhook_id = fields.Char('Webhook Id in Shopify')
    delivery_url = fields.Text("Delivery URL")
    webhook_action = fields.Selection([('customers/create', 'Upon the creation of a customer.'),
                                       ('orders', 'When Order is Created')])
    instance_id = fields.Many2one("shopify.instance.integration",
                                  string="This Shopify instance has generated a webhook.",
                                  ondelete="cascade")

    @api.model_create_multi
    def create(self, values):
        """
        This method is used to create a webhook.
        """
        for val in values:
            available_webhook = self.search(
                [('instance_id', '=', val.get('instance_id')), ('webhook_action', '=', val.get('webhook_action'))],
                limit=1)
            if available_webhook:
                raise UserError(_('Webhook is already created with the same action.'))

            result = super(ShopifyWebhook, self).create(val)
            result.get_webhook()
        return result

    def get_webhook(self):
        """
        Creates webhook in Shopify Store for webhook in Odoo if no webhook is
        there, otherwise updates status of the webhook, if it exists in Shopify store.
        """
        instance_obj = self.instance_id
        instance_obj.connect_in_shopify()
        route = self.get_route()
        current_url = instance_obj.get_base_url()
        shopify_webhook = shopify.Webhook()
        url = current_url + route
        if url[:url.find(":")] == 'http':
            raise UserError(_("Address protocol http:// is not supported for creating the webhooks."))

        webhook_vals = {"topic": self.webhook_action, "address": url, "format": "json"}
        response = shopify_webhook.create(webhook_vals)
        if response.id:
            new_webhook = response.to_dict()
            self.write({"webhook_id": new_webhook.get("id"), 'delivery_url': url, 'state': 'active'})
        return True

    def get_route(self):
        """
        Gives delivery URL for the webhook as per the Webhook Action.
        """
        webhook_action = self.webhook_action
        if webhook_action == 'customers/create':
            route = "/shopify_odoo_webhook_for_customer_create"
        elif webhook_action == 'orders':
            route = "/shopify_odoo_webhook_for_orders_create"
        return route
