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
    webhook_id = fields.Char(string='Bc Webhook ID')


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
        webhook_detail = conn.json()
        self.webhook_id = webhook_detail.get('id')
    
    def delete_bigcommerce_wegbhook(self):
        headers = {
            'accept': "application/json",
            'content-type': "application/json",
            'x-auth-client': '{}'.format(self.bigcommerce_store_id.bigcommerce_x_auth_client),
            'x-auth-token': '{}'.format(self.bigcommerce_store_id.bigcommerce_x_auth_token),
        }
        url = "%s%s/v2/hooks/%s"%(self.bigcommerce_store_id.bigcommerce_api_url,self.bigcommerce_store_id.bigcommerce_store_hash,self.webhook_id)
        response = request(method="DELETE",url=url,headers=headers)
        _logger.warning('>>>>>>>>>>>>>>> \n \n \n Webhook Deleted >>>>>>' )
        self.webhook_id = False
        