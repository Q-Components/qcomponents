from odoo.exceptions import ValidationError
from odoo import models, fields, api, _
import xml.etree.ElementTree as etree
import logging
from odoo.addons.ups_shipping_odoo_integration.models.ups_response import Response
_logger = logging.getLogger(__name__)
import requests

class UpsSaleOrder(models.Model):
    _inherit = "sale.order"

    ups_shipping_location_ids = fields.One2many("ups.location", "ups_sale_order_id",
                                                      string="UPS Locations")
    ups_shipping_location_id = fields.Many2one("ups.location", string="UPS Locations",
                                                     help="UPS Locations", copy=False)
    ups_service_rate = fields.Float(string = "UPS Rate", copy=False)

    def location_api_request_data(self):
        """ this method return request data of location api"""
        recipient_address = self.partner_shipping_id

        # check Receiver Address
        if not recipient_address.zip or not recipient_address.city or not recipient_address.country_id:
            raise ValidationError("Please Define Proper Recipient Address!")
        if not self.carrier_id.company_id:
            raise ValidationError("Credential not available!")

        master_node_AccessRequest = etree.Element("AccessRequest")
        master_node_AccessRequest.attrib['xml:lang'] = "en-US"
        etree.SubElement(master_node_AccessRequest,'AccessLicenseNumber').text ="{}".format(self.company_id.access_license_number)
        etree.SubElement(master_node_AccessRequest, 'UserId').text = "{}".format(self.company_id.ups_userid)
        etree.SubElement(master_node_AccessRequest, 'Password').text = "{}".format(self.company_id.ups_password)
        master_node_LocatorRequest = etree.Element("LocatorRequest")
        sub_root_node_Request = etree.SubElement(master_node_LocatorRequest, 'Request')
        etree.SubElement(sub_root_node_Request, "RequestAction").text = "Locator"
        etree.SubElement(sub_root_node_Request, "RequestOption").text = "{}".format(self.carrier_id and self.carrier_id.ups_request_option)
        sub_root_node_OriginAddress = etree.SubElement(master_node_LocatorRequest, "OriginAddress")
        sub_root_node_AddressKeyFormat = etree.SubElement(sub_root_node_OriginAddress, 'AddressKeyFormat')
        etree.SubElement(sub_root_node_AddressKeyFormat, 'AddressLine').text = "{}".format(recipient_address.street)
        etree.SubElement(sub_root_node_AddressKeyFormat, 'PoliticalDivision2').text = "{}".format(recipient_address.city)
        etree.SubElement(sub_root_node_AddressKeyFormat, 'PoliticalDivision1').text = "{}".format(recipient_address.state_id.code)
        etree.SubElement(sub_root_node_AddressKeyFormat, 'PostcodePrimaryLow').text = "{}".format(recipient_address.zip)
        etree.SubElement(sub_root_node_AddressKeyFormat, 'CountryCode').text = "{}".format(
            recipient_address.country_id.code)
        sub_root_node_Translate = etree.SubElement(master_node_LocatorRequest, "Translate")
        etree.SubElement(sub_root_node_Translate, 'LanguageCode').text = "{}".format("ENG")
        sub_root_node_UnitOfMeasurement = etree.SubElement(master_node_LocatorRequest, "UnitOfMeasurement")
        etree.SubElement(sub_root_node_UnitOfMeasurement, 'Code').text = "{}".format(self.carrier_id and self.carrier_id.ups_measurement_code)
        sub_root_node_LocationSearchCriteria = etree.SubElement(master_node_LocatorRequest, 'LocationSearchCriteria')
        sub_root_node_ServiceSearch = etree.SubElement(sub_root_node_LocationSearchCriteria, "ServiceSearch")
        sub_root_node_ServiceCode = etree.SubElement(sub_root_node_ServiceSearch, 'ServiceCode')
        etree.SubElement(sub_root_node_ServiceCode, 'Code').text = "{}".format(self.carrier_id and self.carrier_id.ups_service_code)
        _reqString = etree.tostring(master_node_AccessRequest)

        tree = etree.ElementTree(etree.fromstring(_reqString))
        root = tree.getroot()

        _QuantunmRequest = etree.tostring(master_node_LocatorRequest)
        quantunmTree = etree.ElementTree(etree.fromstring(_QuantunmRequest))
        quantRoot = quantunmTree.getroot()
        _XmlRequest = etree.tostring(root, encoding='utf8', method='xml') + etree.tostring(quantRoot, encoding='utf8',
                                                                                     method='xml')
        _XmlRequest = _XmlRequest.decode().replace('\n', '')
        return _XmlRequest

    def get_locations(self):
        """ this method return ups location"""
        if not self.carrier_id and self.carrier_id.prod_environment:
            api_url = 'https://wwwcie.ups.com/ups.app/xml/Locator'
        else:
            api_url = 'https://onlinetools.ups.com/ups.app/xml/Locator'
        request_data = self.location_api_request_data()
        try:
            response_data = requests.post(url=api_url,data=request_data)
            if response_data.status_code in [200,201]:
                _logger.info("Get Successfully Response From {}".format(api_url))
                response_data = Response(response_data)
                result = response_data.dict()
                drop_location =result.get('LocatorResponse').get('SearchResults').get('DropLocation')
                if not drop_location:
                    raise ValidationError("Drop Location Not Found {}".format(result))
                ups_locations = self.env['ups.location']
                existing_records = self.env['ups.location'].search(
                    [('ups_sale_order_id', '=', self.id)])
                existing_records.sudo().unlink()
                for location in drop_location:
                    location_id = location.get('LocationID')
                    location_name = location.get('AddressKeyFormat').get('ConsigneeName', '')
                    location_street = location.get('AddressKeyFormat').get('AddressLine')
                    location_city = location.get('AddressKeyFormat').get('PoliticalDivision2')
                    location_area = location.get('AddressKeyFormat').get('PoliticalDivision3')
                    location_state = location.get('AddressKeyFormat').get('PoliticalDivision1')
                    location_zip = location.get('AddressKeyFormat').get('PostcodePrimaryLow')
                    location_country_code =location.get('AddressKeyFormat').get('CountryCode')
                    sale_order_id = self.id
                    ups_locations.sudo().create(
                        {
                            'location_name': location_name,
                            'location_id':"{}".format(location_id),
                            'street':'{}'.format(location_street),
                            'street2': '{}'.format(location_area),
                            'city': '{}'.format(location_city),
                            'state_code': '{}'.format(location_state),
                            'zip': '{}'.format(location_zip),
                            'country_code': '{}'.format(location_country_code),
                            'ups_sale_order_id': '{}'.format(sale_order_id),
                        }
                    )
            else:
                raise ValidationError(response_data.text)
        except Exception as E:
            raise ValidationError(E)

