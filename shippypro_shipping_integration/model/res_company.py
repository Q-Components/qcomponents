from odoo import fields, models, _
import requests
import json
import logging
from requests.auth import HTTPBasicAuth
from odoo.exceptions import ValidationError

_logger = logging.getLogger("Shippypro")


class ResCompany(models.Model):
    _inherit = 'res.company'

    use_shippypro_shipping_service = fields.Boolean(copy=False, string="Are You Using Shippypro?",
                                                    help="If use Shippypro Shipping  Service than value set TRUE.",
                                                    default=False)
    shippypro_api_key = fields.Char(string="Shippypro API KEY")
    shippypro_api_url = fields.Char(string="Shippypro API URL", default="https://www.shippypro.com/api")

    def import_carrier_from_shippypro(self):
        """
                :returns this method import all carrier from Shippypro
                """
        request_data = {
            "Method": "GetCarriers",
            "Params": {}
        }
        headers = {
            'Content-Type': 'application/json'
        }
        try:
            _logger.info(">>> sending get request to {}".format(self.shippypro_api_url))
            response_data = requests.post(url=self.shippypro_api_url,
                                          auth=HTTPBasicAuth(username=self.shippypro_api_key, password=""),
                                          headers=headers, data=json.dumps(request_data))
            if response_data.status_code in [200, 201, 202]:
                _logger.info(">>> get successfully response from {}".format(self.shippypro_api_url))
                _logger.info(">>>> Response Data {}".format(response_data.json()))
                response_data = response_data.json()
                carriers = response_data.get('Carriers')
                if carriers:
                    for key, values in list(carriers.items()):
                        for carrier_values in values:
                            carrier_id = self.env['shippypro.carrier'].search(
                                [('carrier_id', '=', carrier_values.get('CarrierID'))])
                            if not carrier_id:
                                vals = {
                                    "name": key,
                                    "carrier_label": carrier_values.get('Label'),
                                    "carrier_id": carrier_values.get('CarrierID'),
                                    "carrier_service": carrier_values.get('CarrierService')
                                }
                                self.env['shippypro.carrier'].create(vals)
                                _logger.info("Successfully Create Carrier Into Odoo {}".format(carrier_values.get('Label')))
                            else:
                                _logger.info("Carrier Already Exist into Odoo")
                else:
                    raise ValidationError(_('Carrier Not Found Into Response \n {}').format(response_data))
            else:
                raise ValidationError(_('get some error from {0} \n response data {1}').format(self.shippypro_api_url,
                                                                                               response_data.content))
        except Exception as error:
            raise ValidationError(error)
