from odoo import fields,models,api
from requests import request
import logging
import json
_logger = logging.getLogger("Bigcommerce")

class WebhookConfiguration(models.Model):
    _name = 'bigcommerce.webhook.configuration'

    bigcommerce_webhook_version = fields.Char(string='Bigcommerce Webhook Version')
    bigcommerce_webhook_url = fields.Char(string= 'Bigcommerce Webhook Destination Url')
    bigcommerce_webhook_scope = fields.Char(string='Bigcommerce Webhook Scope')
    bigcommerce_store_id = fields.Many2one('bigcommerce.store.configuration',string='Bigcommerce Store')


    def create_bigcommerce_wegbhook(self):
        data = {
            "scope": "{}".format(self.bigcommerce_webhook_scope),
            "destination":  self.bigcommerce_webhook_url + self.bigcommerce_webhook_scope,
            "is_active": True
        }

        headers = {
            'accept': "application/json",
            'content-type': "application/json",
            'x-auth-client': '{}'.format(self.bigcommerce_store_id.bigcommerce_x_auth_client),
            'x-auth-token': '{}'.format(self.bigcommerce_store_id.bigcommerce_x_auth_token),
        }

        conn = request(method="POST",url=(self.bigcommerce_store_id.bigcommerce_api_url + self.bigcommerce_store_id.bigcommerce_store_hash + '/' + self.bigcommerce_webhook_version + '/hooks'), headers=headers, data=json.dumps(data))
        _logger.warning('>>>>>>>>>>>>>>> \n \n \n connection >>>>>>>%s' % (conn.text))