import requests
import json
import logging
from odoo import models, fields
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    use_ups_third_party_account = fields.Boolean(string='UPS Bill To Recipient')
    ups_third_party_account_id = fields.Many2one('ups.thirdparty.account', string='UPS Third Party Account')

    ups_shipping_location_ids = fields.One2many("ups.location", "ups_sale_order_id",
                                                string="UPS Locations")
    ups_shipping_location_id = fields.Many2one("ups.location", string="UPS Locations",
                                               help="UPS Locations", copy=False)

    def get_ups_locations(self):
        """ this method return ups location"""
        recipient_address_id = self.partner_shipping_id
        company_id = self.company_id
        receiver_zip = recipient_address_id.zip or ""
        receiver_city = recipient_address_id.city or ""
        receiver_country_code = recipient_address_id.country_id and recipient_address_id.country_id.code or ""
        receiver_state_code = recipient_address_id.state_id and recipient_address_id.state_id.code or ""
        receiver_street = recipient_address_id.street or ""
        # check Receiver Address
        if not receiver_zip or not receiver_city or not receiver_country_code:
            raise ValidationError("Please Define Proper Recipient Address!")
        if not self.carrier_id.company_id:
            raise ValidationError("Carrier not available!")
        request_data = json.dumps({
            "LocatorRequest": {
                "Request": {
                    "TransactionReference": {"CustomerContext": ""},
                    "RequestAction": "Locator",
                    "RequestOption": "{}".format(self.carrier_id and self.carrier_id.ups_request_option)},
                "OriginAddress": {
                    "AddressKeyFormat": {
                        "AddressLine": receiver_street,
                        "PoliticalDivision2": "{}".format(receiver_city),
                        "PoliticalDivision1": "{}".format(receiver_state_code),
                        "PostcodePrimaryLow": "{}".format(receiver_zip),
                        "CountryCode": "{}".format(receiver_country_code)}
                },
                "Translate": {"LanguageCode": "ENG"},
                "UnitOfMeasurement": {
                    "Code": "{}".format(self.carrier_id and self.carrier_id.ups_measurement_code)},
                "LocationSearchCriteria": {
                    "ServiceSearch": {
                        "ServiceCode": {"Code": "{}".format(self.carrier_id and self.carrier_id.ups_service_code)}
                    }
                }
            }
        })
        api_url = "{}/api/locations/v1/search/availabilities/64?Locale=en_US".format(company_id.ups_api_url)
        _logger.info("UPS Location API URL {}".format(api_url))
        _logger.info("UPS Location Request DATA {}".format(request_data))
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json',
                   'Authorization': "Bearer {}".format(company_id.ups_api_token)}
        try:
            response = requests.request("POST", api_url, headers=headers, data=request_data)
            if response.status_code in [200, 201]:
                Locator_data = response.json()
                _logger.info("UPS Location Response DATA {}".format(Locator_data))
                drop_location = Locator_data.get('LocatorResponse') and Locator_data.get('LocatorResponse').get(
                    'SearchResults') and Locator_data.get('LocatorResponse').get('SearchResults').get('DropLocation')
                if not drop_location:
                    raise ValidationError("Drop Location Not Found {}".format(Locator_data))
                ups_locations = self.env['ups.location']
                existing_records = self.env['ups.location'].search([('ups_sale_order_id', '=', self.id)])
                existing_records.sudo().unlink()
                for location in drop_location:
                    country_obj = self.env['res.country'].search(
                        [('code', '=', location.get('AddressKeyFormat').get('CountryCode'))])
                    state_name = location.get('AddressKeyFormat') and location.get('AddressKeyFormat').get(
                        'PoliticalDivision1')
                    if state_name:
                        state_code_obj = [state_name.capitalize(), state_name.lower(), state_name.upper()]
                        state_code = self.env['res.country.state'].search(
                            ["|", ('name', 'in', state_code_obj), ('code', '=', state_name),
                             ('country_id', '=', country_obj.id)])
                        if state_code:
                            state_name_code = state_code.code
                        else:
                            state_name_code = ""
                    else:
                        state_name_code = ""

                    ups_locations.sudo().create(
                        {'name': "{}".format(location.get('AddressKeyFormat').get('ConsigneeName')),
                         'location_id': "{}".format(location.get('LocationID')),
                         'street': '{}'.format(location.get('AddressKeyFormat').get('AddressLine')),
                         'street2': '{}'.format(location.get('AddressKeyFormat').get('PoliticalDivision3')),
                         'city': '{}'.format(location.get('AddressKeyFormat').get('PoliticalDivision2')),
                         'state_code': '{}'.format(state_name_code),
                         'zip': '{}'.format(location.get('AddressKeyFormat').get('PostcodePrimaryLow')),
                         'country_code': '{}'.format(location.get('AddressKeyFormat').get('CountryCode')),
                         'ups_sale_order_id': '{}'.format(self.id)})
                return {
                    'effect': {
                        'fadeout': 'slow',
                        'message': "Yeah! UPS Locations Retrieved successfully!!",
                        'img_url': '/web/static/img/smile.svg',
                        'type': 'rainbow_man',
                    }
                }
            else:
                raise ValidationError(response.text)
        except Exception as E:
            raise ValidationError(E)
