from odoo import fields,models,api


class BigcommerceWebhookIds(models.Model):
    _inherit = 'bigcommerce.store.configuration'

    bigcommerce_webhook_ids = fields.One2many('bigcommerce.webhook.configuration', 'bigcommerce_store_id',
                                              string='Webhook Configuration')