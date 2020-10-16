from odoo import fields,models,api


class BigcommerceWebhookIds(models.Model):
    _inherit = 'bigcommerce.store.configuration'

    bigcommerce_webhook_ids = fields.One2many('bigcommerce.webhook.configuration', 'bigcommerce_store_id',
                                              string='Webhook Configuration')
    
    def auto_delete_and_create_webhook(self):
        store_config = self.env['bigcommerce.store.configuration'].search([])
        for store_id in store_config:
            for webhook in store_id.bigcommerce_webhook_ids:
                webhook.delete_bigcommerce_wegbhook()
                webhook.create_bigcommerce_wegbhook()
                self._cr.commit()
