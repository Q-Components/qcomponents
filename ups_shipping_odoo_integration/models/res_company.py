import requests
import base64
from odoo import models, fields
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    use_ups_shipping_provider = fields.Boolean(copy=False, string="Are You Use UPS Shipping Provider.?",
                                               help="If use UPS shipping provider than value set TRUE.",
                                               default=False)
    ups_api_url = fields.Char(string="API URL", copy=False, default="https://wwwcie.ups.com")
    ups_userid = fields.Char("UPS User ID")
    ups_password = fields.Char("UPS Password")
    ups_shipper_number = fields.Char("UPS Shipper Number")
    ups_api_token = fields.Char(string='UPS Token')
    ups_client_id = fields.Char(string='Client ID')
    ups_client_secret = fields.Char(string='Client Secret')

    def ups_generate_token(self):
        payload = 'grant_type=client_credentials'
        api_secret = self.ups_client_secret
        api_key = self.ups_client_id
        data = "{0}:{1}".format(api_key, api_secret)
        encode_data = base64.b64encode(data.encode("utf-8"))
        authrization_data = "Basic {}".format(encode_data.decode("utf-8"))
        headers = {"Authorization": authrization_data,
                   "Content-Type": "application/x-www-form-urlencoded"}
        url = "%s/security/v1/oauth/token" % (self.ups_api_url)
        try:
            response = requests.request("POST", url, headers=headers, data=payload)
            if response.status_code in [200, 201]:
                response_data = response.json()
                if response_data['access_token']:
                    self.ups_api_token = response_data['access_token']
                    return {
                        'effect': {
                            'fadeout': 'slow',
                            'message': "Yeah! UPS Token Retrieved successfully!!",
                            'img_url': '/web/static/img/smile.svg',
                            'type': 'rainbow_man',
                        }
                    }
                else:
                    raise ValidationError(response_data)
            else:
                raise ValidationError(response.text)
        except Exception as e:
            raise ValidationError(e)

    def ups_generate_crone(self):
        for company_id in self.search([('use_ups_shipping_provider', '=', True)]):
            company_id.ups_generate_token()
