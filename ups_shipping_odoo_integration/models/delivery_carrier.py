import logging
import requests
import json
import binascii
import io
import base64
import PIL.PdfImagePlugin  # activate PDF support in PIL
from PIL import Image

from odoo.tools import pdf
from odoo import models, fields, tools ,_
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(selection_add=[("ups_provider", "UPS")],
                                     ondelete={'ups_provider': 'set default'})
    ups_provider_package_id = fields.Many2one('stock.package.type', string="Package Info", help="Default Package")
    ups_service_type = fields.Selection([('01', '01-Next Day Air'),
                                         ('02', '02-2nd Day Air'),
                                         ('03', '03-Ground'),
                                         ('12', '12-3 Day Select'),
                                         ('13', '13-Next Day Air Saver'),
                                         ('14', '14-UPS Next Day Air Early'),
                                         ('59', '59-2nd Day Air A.M.'),
                                         ('07', '07-Worldwide Express'),
                                         ('08', '08-Worldwide Expedited'),
                                         ('11', '11-Standard'),
                                         ('54', '54-Worldwide Express Plus'),
                                         ('65', '65-Saver'),
                                         ('96', '96-UPS Worldwide Express Freight'),
                                         ('70', '70- UPS Access Point™ Economy'),
                                         ('92', 'UPS SurePost Less than 1LB'),
                                         ('93', 'UPS SurePost 1LB or greater'),
                                         ('94', 'UPS SurePost BPM'),
                                         ('95', 'UPS SurePost Media Mail'),
                                         ], string="Service Types")
    ups_weight_uom = fields.Selection([('LBS', 'LBS-Pounds'),
                                       ('KGS', 'KGS-Kilograms'),
                                       ('OZS', 'OZS-Ounces')], string="Weight UOM", help="Weight UOM of the Shipment")
    ups_label_print_methods = fields.Selection([('GIF', 'PDF'),
                                                ('ZPL', 'ZPL')], string="Label File Type",
                                               help="Specifies the type of label formate.", default="GIF")
    negotiated_rate = fields.Boolean("Negotiate Rate")
    commercial_invoice = fields.Boolean("Commercial Invoice")

    # If Need to use Location functionality in that case we can use this field
    ups_pickup_functionality = fields.Boolean(string='Use Pickup/Location Functionality',
                                              help="If you want's to use pickup get functionality then we need to enable this options")
    ups_measurement_code = fields.Selection([('MI', 'MI Miles'), ('KM ', 'KM Kilometers')], string="UPS Measurement")
    ups_request_option = fields.Selection([('1', '1 A list of locations'),
                                           ('8', '8 All available additional services'),
                                           ('16', '16 All available program types'),
                                           ('24', '24 All available additional services and program types'),
                                           ('32', '32 All available retail locations'),
                                           ('40', '40 All available retail locations and additional services'),
                                           ('48', '48 All available retail locations and program types'),
                                           ('56',
                                            '56 All available retail locations, program types, and additional services'),
                                           ('64', '64 UPS Access Point Search')], string="UPS Request Option",
                                          help="The RequestOption element is used to define the type of location information that will be provided.")
    ups_service_code = fields.Selection([('01', '01 Ground'),
                                         ('02', '02 Air'),
                                         ('03', '03 Express'),
                                         ('04', '04 Standard'),
                                         ('05', '05 International')], string="UPS Service Code",
                                        help="Container that contains the service information such as Ground/Air")
    # For COD Fields
    ups_cod_parcel = fields.Boolean(string='COD')
    ups_cod_service = fields.Selection(
        [("shipment_level", "Shipment Level"), ('package_level', 'Package Level')], string="UPS COD Service",
        help="Shipment Level : All European Union (EU) Countries or Territories supported by the API.(1,9)"
             "Package Level :  No EU countries or territories currently support Package level COD.(0,8,9)",
        default="shipment_level")
    ups_cod_fund_code = fields.Selection(
        [('0', '0 - Check, Cash Cashier Check Money Order'), ('8', '8 - Cashier Check Money Order'), ('1', '1 - Cash'),
         ('9', '9 - Check Cashiers Check Money Order/Personal Check')],
        help="Shipment Level = 1 or 9: "
             "Package Level : 0 or 8 or 9", string="UPS COD Fund Code", default="1")

    # For Insurance funcionality
    insured_request = fields.Boolean(string="Insured Request",
                                     help="Use this Insured Request required, UPS rate comes with signatured cost.",
                                     default=False)

    # for signature
    signature_required = fields.Selection([('1', 'Delivery Confirmation'),
                                           ('2', 'Delivery Confirmation Signature Required'),
                                           ('3', 'Delivery Confirmation Adult Signature Required')],
                                          string="Signature Required",
                                          help="Delivery Confirmation container")
    # for Saturday Service
    saturdaydelivery = fields.Boolean(string="SaturdayDelivery",
                                      help="",
                                      default=False)
    return_labels = fields.Boolean(string="Return Label",
                                   help="If the boolean value is true, the return label will automatically be attached to the shipment label",
                                   default=False)
    ups_shipment_indication_type = fields.Selection([('01', 'Hold for Pickup at UPS Access Point'),
                                                     ('02', 'UPS Access Point™ Delivery')],
                                                    string="Shipment Indication Type",
                                                    help="'01' - Hold for Pickup at UPS Access Point aka Direct to Retail (D2R),\n'02' - UPS Access Point™ Delivery aka Retail to Retail (R2R) If '01' code is present indicates shipment will be send to Retail location where it is held to consignee to claim.")
    ups_notification_type = fields.Selection([('5', '5 - QV In-transit Notification'),
                                              ('6', '6 - QV Ship Notification'),
                                              ('7', '7 - QV Exception Notification'),
                                              ('8', '8 - QV Delivery Notification'),
                                              ('2', '2 - Return Notification or Label Creation Notification'),
                                              ('012', '012 - Alternate Delivery Location Notification'),
                                              ('013', '013 - UAP Shipper Notification')],
                                             string="Notification Type",
                                             help="The type of notification requested")

    def check_address_details(self, address_id, required_fields):
        """
            check the address of Shipper and Recipient
            param : address_id: res.partner, required_fields: ['zip', 'city', 'country_id', 'street']
            return: missing address message
        """

        res = [field for field in required_fields if not address_id[field]]
        if res:
            return "Missing Values For Address :\n %s" % ", ".join(res).replace("_id", "")

    def retreive_adderess_details(self, address_id):
        return {
            "AddressLine": [address_id.street and address_id.street[:35] or " ",
                            address_id.street2 and address_id.street2[:35] or " "],
            "City": address_id.city or "",
            "StateProvinceCode": address_id.state_id and address_id.state_id.code or "",
            "PostalCode": address_id.zip or "",
            "CountryCode": address_id.country_id and address_id.country_id.code or ""
        }

    def collect_address_details(self, address_id, is_send_shipper_number=False):
        address_dict = {"Name": address_id.name[:34] or "",
                        "AttentionName": address_id.name[:34] or "",
                        "TaxIdentificationNumber": self.company_id.vat or "",
                        "Phone": {
                            "Number": address_id.phone and address_id.phone.replace(' ','')[:15] or ""
                        },
                        "Address": self.retreive_adderess_details(address_id)
                        }
        if is_send_shipper_number:
            address_dict.update({"ShipperNumber": self.company_id.ups_shipper_number, })
        return address_dict

    def ups_provider_rate_shipment(self, order):
        """
           This method is used for get rate of shipment
           param : order : sale.order
           return: 'success': False : 'error message' : True
           return: 'success': True : 'error_message': False
        """
        # Shipper and Recipient Address
        shipper_address_id = order.warehouse_id.partner_id
        recipient_address_id = order.partner_shipping_id
        company_id = self.company_id

        shipper_address_error = self.check_address_details(shipper_address_id,
                                                           ['zip', 'city', 'country_id', 'street'])
        recipient_address_error = self.check_address_details(recipient_address_id,
                                                             ['zip', 'city', 'country_id', 'street'])
        total_weight = sum([(line.product_id.weight * line.product_uom_qty) for line in order.order_line]) or 0.0

        product_weight = (order.order_line.filtered(
            lambda x: not x.is_delivery and x.product_id.type == 'consu' and x.product_id.weight <= 0))
        product_name = ", ".join(product_weight.mapped('product_id').mapped('name'))
        package_id = self.ups_provider_package_id
        if not package_id:
            raise ValidationError("Package Details Not Correct!!")
        if shipper_address_error or recipient_address_error or product_name or not recipient_address_id.phone:
            return {'success': False, 'price': 0.0,
                    'error_message': "%s %s  %s %s" % (
                        "Shipper Address : %s \n" % (shipper_address_error) if shipper_address_error else "",
                        "Recipient Address : %s \n" % (recipient_address_error) if recipient_address_error else "",
                        "product weight is not available : %s" % (product_name) if product_name else "",
                        "Telephone number in contact is mandatory : %s" % (
                            recipient_address_id.name) if not recipient_address_id.phone else ""
                    ),
                    'warning_message': False}
        try:
            payload = ({"RateRequest": {"Request": {"RequestOption": "Rate"},
                                        "Shipment": {"Shipper": self.collect_address_details(shipper_address_id,
                                                                                             is_send_shipper_number=True),
                                                     "ShipTo": self.collect_address_details(recipient_address_id),
                                                     "ShipFrom": self.collect_address_details(shipper_address_id),
                                                     "Service": {"Code": self.ups_service_type},
                                                     "Package": [
                                                         {
                                                             "PackagingType": {
                                                                 "Code": "%s" % (package_id.shipper_package_code)},
                                                             "Dimensions": {
                                                                 "UnitOfMeasurement": {
                                                                     "Code": str(
                                                                         "IN" if self.ups_weight_uom != "KGS" else "CM")
                                                                 },
                                                                 "Length": "%s" % (package_id.packaging_length or "0"),
                                                                 "Width": "%s" % (package_id.width or "0"),
                                                                 "Height": "%s" % (package_id.height or "0")
                                                             },
                                                             "PackageWeight": {
                                                                 "UnitOfMeasurement": {
                                                                     "Code": "%s" % (self.ups_weight_uom)},
                                                                 "Weight": str(total_weight)
                                                             }
                                                         }
                                                     ]
                                                     }
                                        }
                        })
            if self.negotiated_rate:
                negotiatedrate = payload.get('RateRequest').get('Shipment')
                negotiatedrate.update({"ShipmentRatingOptions": {"NegotiatedRatesIndicator": ""}})
            if self.ups_shipment_indication_type:
                shipment_indication_type = payload['RateRequest']['Shipment']
                shipment_indication_type.update({
                    "AlternateDeliveryAddress": {
                        "Address": self.retreive_adderess_details(shipper_address_id)
                    },
                    "ShipmentIndicationType": [
                        {
                            "Code": self.ups_shipment_indication_type
                        }
                    ],
                })
            if self.signature_required:
                origin = shipper_address_id.country_id.code
                destination = recipient_address_id.country_id.code

                if (origin, destination) in [("US", "US"), ("US", "PR"), ("CA", "CA"), ("PR", "US"), ("PR", "PR")]:
                    payload['RateRequest']['Shipment']['Package'][0].update({
                        "PackageServiceOptions": {
                            "DeliveryConfirmation": {
                                "DCISType": self.signature_required
                            }
                        }
                    })
                elif self.signature_required in ['2', '3']:
                    signature_required = '1' if self.signature_required == '2' else '2'
                    payload['RateRequest']['Shipment'].update({
                        "ShipmentServiceOptions": {
                            "DeliveryConfirmation": {
                                "DCISType": signature_required
                            }
                        }})

            header = {'Authorization': "Bearer {}".format(self.company_id.ups_api_token),
                      'Content-Type': 'application/json'}
            api_url = "{}/api/rating/v1/Rate".format(company_id.ups_api_url)
            request_data = json.dumps(payload)
            request_type = "POST"
            response_status, response_data = self.ups_provider_create_shipment(request_type, api_url, request_data,
                                                                               header)
            if response_status:
                rate_shipment = response_data.get('RateResponse') and response_data.get('RateResponse').get(
                    'RatedShipment')
                if not rate_shipment:
                    return {'success': False, 'price': 0.0,
                            'error_message': response_data, 'warning_message': False}
                if self.negotiated_rate:
                    rate_price = rate_shipment.get('NegotiatedRateCharges') and rate_shipment.get(
                        'NegotiatedRateCharges').get('TotalCharge') and rate_shipment.get('NegotiatedRateCharges').get(
                        'TotalCharge').get(
                        'MonetaryValue') or rate_shipment.get('TotalCharges') and rate_shipment.get('TotalCharges').get(
                        'MonetaryValue')
                else:
                    rate_price = rate_shipment.get('TotalCharges') and rate_shipment.get('TotalCharges').get(
                        'MonetaryValue')
                return {'success': True, 'price': rate_price or 0.0,
                        'error_message': False, 'warning_message': False}
            else:
                request_data = json.loads(response_data)
                error_data = request_data.get('response').get('errors')
                for error in error_data:
                    if error.get('code') == '111035':
                        return {'success': False, 'price': 0.0,
                                'error_message': "Not Eligible Order Size too large to go by UPS - would be shipped by LTL Freight",
                                'warning_message': False}
                    else:
                        return {'success': False, 'price': 0.0,
                                'error_message': response_data, 'warning_message': False}
        except Exception as e:
            return {'success': False, 'price': 0.0,
                    'error_message': e, 'warning_message': False}

    def ups_get_shipping_amount(self, picking_id):
        shipping_amount = (picking_id.sale_id.order_line.filtered(lambda
                                                                      order_line: order_line.is_delivery == True).price_total if picking_id.sale_id.order_line.filtered(
            lambda order_line: order_line.is_delivery == True) else 0.0) / (
                                  len(picking_id.move_line_ids.mapped('result_package_id')) + (
                              1 if picking_id.weight_bulk else 0))
        return shipping_amount

    def ups_provider_packages(self, picking):
        package_list = []
        weight_bulk = picking.weight_bulk
        package_ids = picking.move_line_ids.mapped('result_package_id')
        parcel_value_for_bulk_weight = 0.0
        parcel_value_for_all_package_amount = 0.0
        sale_line_added = []
        mrp_module = self.env['ir.module.module'].search([('name','=','mrp')])
        package_signature = False
        for package_id in package_ids:
            package_amount = 0.0
            parcel_value_for_package = 0.0
            height = package_id.package_type_id and package_id.package_type_id.height or 0
            width = package_id.package_type_id and package_id.package_type_id.width or 0
            length = package_id.package_type_id and package_id.package_type_id.packaging_length or 0
            weight = package_id.shipping_weight
            for quant_id in package_id.quant_ids:
                product_id = quant_id.product_id
                move_line = self.env['stock.move.line'].search(
                    [('picking_id', '=', picking.id), ('result_package_id', '=', package_id.id),
                     ('product_id', '=', product_id.id)], limit=1)
                _logger.info("Move Lines : {}".format(move_line))
                if picking.sale_id:
                    if mrp_module and mrp_module.state == 'installed':
                        if move_line.move_id.bom_line_id and move_line.move_id.bom_line_id.bom_id.mapped('product_id'):
                            product_id = move_line.move_id.bom_line_id.bom_id.product_id
                            find_sale_line_id = picking.sale_id.order_line.filtered(
                                lambda x: x.product_id.id == product_id.id and move_line.move_id.sale_line_id.id == x.id)
                        elif move_line.move_id.bom_line_id and move_line.move_id.bom_line_id.bom_id and move_line.move_id.bom_line_id.bom_id.mapped('product_tmpl_id'):
                            product_tmpl_id = move_line.move_id.bom_line_id.bom_id.product_tmpl_id
                            _logger.info("Bom Line : {}".format(move_line.move_id.sale_line_id))
                            find_sale_line_id = picking.sale_id.order_line.filtered(
                                lambda
                                    x: x.product_id.product_tmpl_id.id == product_tmpl_id.id and move_line.move_id.sale_line_id.id == x.id)[
                                0]
                        else:
                            # _logger.info("UPS Package Product:{}".format(product_id))
                            find_sale_line_id = picking.sale_id.order_line.filtered(
                                lambda x: x.product_id.id == product_id.id and move_line.move_id.sale_line_id.id == x.id)
                            find_sale_line_id = find_sale_line_id and find_sale_line_id[0]
                    else:
                        # _logger.info("UPS Package Product:{}".format(product_id))
                        find_sale_line_id = picking.sale_id.order_line.filtered(
                            lambda x: x.product_id.id == product_id.id and move_line.move_id.sale_line_id.id == x.id)
                        find_sale_line_id = find_sale_line_id and find_sale_line_id[0]
                    _logger.info("PACKAGE : Sale Line:{}".format(find_sale_line_id))
                    if find_sale_line_id.id in sale_line_added:
                        continue
                    if not find_sale_line_id or not find_sale_line_id.product_uom_qty:
                        raise ValidationError("Proper data of sale order lines not found.")
                    if mrp_module and mrp_module.state == 'installed':
                        if move_line.move_id.bom_line_id and move_line.move_id.bom_line_id.bom_id:
                            single_unit_price = find_sale_line_id.price_total / find_sale_line_id.product_uom_qty
                            parcel_value_for_package += single_unit_price * find_sale_line_id.product_uom_qty
                        else:
                            single_unit_price = find_sale_line_id.price_total / find_sale_line_id.product_uom_qty
                            parcel_value_for_package += single_unit_price * quant_id.quantity
                    else:
                        single_unit_price = find_sale_line_id.price_total / find_sale_line_id.product_uom_qty
                        parcel_value_for_package += single_unit_price * quant_id.quantity
                    sale_line_added.append(find_sale_line_id.id)
                else:
                    parcel_value_for_package += quant_id.product_id.lst_price * quant_id.quantity
            parcel_value_for_all_package_amount += parcel_value_for_package
            if not picking.backorder_id:
                shipping_amount = self.ups_get_shipping_amount(picking)
                parcel_value_for_all_package_amount += shipping_amount
            package_data = {
                "Description": package_id.name or "",
                "Packaging": {
                    "Code": "%s" % (
                            package_id.package_type_id and package_id.package_type_id.shipper_package_code)
                },
                "ReferenceNumber": {"Value": package_id.name or ""},
                "Dimensions": {
                    "UnitOfMeasurement": {
                        "Code": "CM" if self.ups_weight_uom == "KGS" else "IN",
                    },
                    "Length": str(length),
                    "Width": str(width),
                    "Height": str(height)
                },
                "PackageWeight": {
                    "UnitOfMeasurement": {
                        "Code": "%s" % (self.ups_weight_uom)
                    },
                    "Weight": str(weight)
                },
                "PackageServiceOptions": {
                    # for signature
                    # Insurance And Declared Value
                }
            }
            package_service_option = package_data.get('PackageServiceOptions')
            # for signature
            if self.signature_required:
                if self.company_id.country_id.code in ["US", "CA", "PR"]:
                    origin = self.company_id.country_id.code
                    destination = picking.partner_id.country_id.code
                    if (origin, destination) in [("US", "US"), ("US", "PR"), ("CA", "CA"), ("PR", "US"), ("PR", "PR")]:
                        package_service_option.update({
                                "DeliveryConfirmation": {"DCISType": self.signature_required}})
                        package_signature = True
            # Insurance And Declared Value
            if self.insured_request:
                package_service_option.update({
                    "DeclaredValue": {
                        "CurrencyCode": '{}'.format(
                            self.company_id and self.company_id.currency_id and self.company_id.currency_id.name or " "),
                        "MonetaryValue": str(parcel_value_for_package)
                    }
                })
            # for COD
            if self.ups_cod_parcel and self.ups_cod_service == "package_level":
                package_service_option.update({"COD": {
                    "CODFundsCode": self.ups_cod_fund_code,
                    "CODAmount": {
                        "CurrencyCode": '{}'.format(
                            self.company_id and self.company_id.currency_id and self.company_id.currency_id.name or " "),
                        "MonetaryValue": str(parcel_value_for_package)
                    }
                }})
            package_list.append(package_data)
        if weight_bulk:
            height = self.ups_provider_package_id and self.ups_provider_package_id.height or 0
            width = self.ups_provider_package_id and self.ups_provider_package_id.width or 0
            length = self.ups_provider_package_id and self.ups_provider_package_id.packaging_length or 0
            weight = weight_bulk
            for rec in picking.move_line_ids:
                if rec.product_id and not rec.result_package_id:
                    product_id = rec.product_id
                    if picking.sale_id:
                        if mrp_module and mrp_module.state == 'installed':
                            if rec.move_id.bom_line_id and rec.move_id.bom_line_id.bom_id and rec.move_id.bom_line_id.bom_id.product_id:
                                product_id = rec.move_id.bom_line_id.bom_id.product_id
                                find_sale_line_id = picking.sale_id.order_line.filtered(lambda x: x.product_id.id == product_id.id and rec.move_id.sale_line_id.id == x.id)
                                find_sale_line_id = find_sale_line_id[0]
                            elif rec.move_id.bom_line_id and rec.move_id.bom_line_id.bom_id.mapped('product_tmpl_id'):
                                product_tmpl_id = rec.move_id.bom_line_id.bom_id.product_tmpl_id
                                find_sale_line_id = picking.sale_id.order_line.filtered(lambda x: x.product_id.product_tmpl_id.id == product_tmpl_id.id and rec.move_id.sale_line_id.id == x.id)
                                find_sale_line_id = find_sale_line_id and find_sale_line_id[0]
                            else:
                                find_sale_line_id = picking.sale_id.order_line.filtered(lambda x: x.product_id.id == product_id.id and rec.move_id.sale_line_id.id == x.id)
                                find_sale_line_id = find_sale_line_id and find_sale_line_id[0]
                        else:
                            find_sale_line_id = picking.sale_id.order_line.filtered(
                                lambda x: x.product_id.id == product_id.id and rec.move_id.sale_line_id.id == x.id)
                            find_sale_line_id = find_sale_line_id and find_sale_line_id[0]
                        if find_sale_line_id.id in sale_line_added:
                            continue
                        sale_line_added.append(find_sale_line_id.id)
                        _logger.info("Bulk Product : {}".format(product_id))
                        if not find_sale_line_id or not find_sale_line_id.product_uom_qty:
                            raise ValidationError("Proper data of sale order lines not found.")
                        single_unit_price = find_sale_line_id.price_total / find_sale_line_id.product_uom_qty
                        if mrp_module and mrp_module.state == 'installed':
                            if rec.move_id.bom_line_id and rec.move_id.bom_line_id.bom_id:
                                parcel_value_for_bulk_weight += single_unit_price * rec.quantity
                            else:
                                parcel_value_for_bulk_weight += find_sale_line_id.price_unit * rec.quantity + find_sale_line_id.price_unit * rec.quantity * ((find_sale_line_id.tax_id and sum(find_sale_line_id.tax_ids.mapped('amount')) or 0.0)/100)
                        else:
                            parcel_value_for_bulk_weight += find_sale_line_id.price_unit * rec.quantity + find_sale_line_id.price_unit * rec.quantity * ((find_sale_line_id.tax_id and sum(find_sale_line_id.tax_ids.mapped('amount')) or 0.0)/100)
                    else:
                        parcel_value_for_bulk_weight = rec.product_id.lst_price * rec.qty_done
            if not picking.backorder_id:
                shipping_amount = self.ups_get_shipping_amount(picking)
                parcel_value_for_bulk_weight += shipping_amount
            package_data = {
                "Description": picking.name[:34] or "",
                "Packaging": {
                    "Code": "%s" % (
                            self.ups_provider_package_id and self.ups_provider_package_id.shipper_package_code)
                },
                "ReferenceNumber": {"Value": picking.name or ""},
                "Dimensions": {
                    "UnitOfMeasurement": {
                        "Code": "CM" if self.ups_weight_uom == "KGS" else "IN",
                    },
                    "Length": str(length),
                    "Width": str(width),
                    "Height": str(height)
                },
                "PackageWeight": {
                    "UnitOfMeasurement": {
                        "Code": "%s" % (self.ups_weight_uom)
                    },
                    "Weight": str(weight)
                },
                "PackageServiceOptions": {
                    # Insurance And Declared Value and Signature
                }
            }
            package_service_option = package_data.get('PackageServiceOptions')
            # for signature
            if self.signature_required:
                if self.company_id.country_id.code in ["US", "CA", "PR"]:
                    origin = self.company_id.country_id.code
                    destination = picking.partner_id.country_id.code
                    if (origin, destination) in [("US", "US"), ("US", "PR"), ("CA", "CA"), ("PR", "US"), ("PR", "PR")]:
                        package_service_option.update({
                            "DeliveryConfirmation": {"DCISType": self.signature_required}})
                        package_signature = True
            # Insurance And Declared Value
            if self.insured_request:
                package_service_option.update({
                    "DeclaredValue": {
                        "CurrencyCode": '{}'.format(
                            self.company_id and self.company_id.currency_id and self.company_id.currency_id.name or " "),
                        "MonetaryValue": str(parcel_value_for_bulk_weight)
                    }
                })
            if self.ups_cod_parcel and self.ups_cod_service == "package_level":
                package_service_option.update({"COD": {
                    "CODFundsCode": self.ups_cod_fund_code,
                    "CODAmount": {
                        "CurrencyCode": '{}'.format(
                            self.company_id and self.company_id.currency_id and self.company_id.currency_id.name or " "),
                        "MonetaryValue": str(parcel_value_for_bulk_weight)
                    }
                }})
            package_list.append(package_data)
        total_ups_cod_amount = parcel_value_for_bulk_weight + parcel_value_for_all_package_amount
        picking.ups_cod_amount = total_ups_cod_amount
        return package_list, total_ups_cod_amount,package_signature

    def ups_provider_create_shipment(self, request_type, api_url, request_data, header):
        _logger.info("Shipment Request API URL:::: %s" % api_url)
        _logger.info("Shipment Request Data:::: %s" % request_data)
        response_data = requests.request(method=request_type, url=api_url, headers=header, data=request_data)
        if response_data.status_code in [200, 201]:
            response_data = response_data.json()
            _logger.info(">>> Response Data {}".format(response_data))
            return True, response_data
        else:
            return False, response_data.text

    def ups_provider_send_shipping(self, picking):
        shipper_address_id = picking.picking_type_id and picking.picking_type_id.warehouse_id and picking.picking_type_id.warehouse_id.partner_id
        recipient_address_id = picking.partner_id
        company_id = self.company_id
        shipper_address_error = self.check_address_details(shipper_address_id,
                                                           ['zip', 'city', 'country_id', 'street'])
        recipient_address_error = self.check_address_details(recipient_address_id,
                                                             ['zip', 'city', 'country_id', 'street'])
        if shipper_address_error or recipient_address_error or not picking.shipping_weight or not recipient_address_id.phone:
            raise ValidationError("%s  %s  %s %s" % (
                "Shipper Address : %s \n" % (shipper_address_error) if shipper_address_error else "",
                "Recipient Address : %s \n" % (recipient_address_error) if recipient_address_error else "",
                "Shipping weight is missing!" if not picking.shipping_weight else "",
                "Telephone number in contact is mandatory : %s" % (
                    recipient_address_id.name) if not recipient_address_id.phone else ""
            ))

        # Location & Pickup(Pickup Point Functionality)
        receiver_street = picking.sale_id.ups_shipping_location_id.street if picking.sale_id.ups_shipping_location_id else recipient_address_id.street or ""
        receiver_street2 = picking.sale_id.ups_shipping_location_id.street2 if picking.sale_id.ups_shipping_location_id else recipient_address_id.street2 or ""
        ship_to_name = picking.sale_id.ups_shipping_location_id.name if picking.sale_id.ups_shipping_location_id else recipient_address_id.name[:34] or ""
        receiver_city = picking.sale_id.ups_shipping_location_id.city if picking.sale_id.ups_shipping_location_id else recipient_address_id.city or ""
        receiver_zip = picking.sale_id.ups_shipping_location_id.zip if picking.sale_id.ups_shipping_location_id else recipient_address_id.zip or ""
        receiver_country_code = picking.sale_id.ups_shipping_location_id.country_code if picking.sale_id.ups_shipping_location_id else recipient_address_id.country_id and recipient_address_id.country_id.code or ""
        receiver_state = picking.sale_id.ups_shipping_location_id.state_code if picking.sale_id.ups_shipping_location_id else recipient_address_id.state_id and recipient_address_id.state_id.code or ""
        account_id_obj = picking and picking.sale_id and picking.sale_id.ups_third_party_account_id
        account_number = account_id_obj and account_id_obj.account_no
        party_zip = account_id_obj and account_id_obj.zip
        party_country = account_id_obj and account_id_obj.country_id and account_id_obj.country_id and account_id_obj.country_id.code
        packages, total_ups_cod_amount,package_signature = self.ups_provider_packages(picking)

        payload = ({
            "ShipmentRequest": {
                "Description": picking.origin or "",
                "Request": {
                    "RequestOption": "nonvalidate"
                },
                "Shipment": {
                    "Description": picking.name,
                    "Shipper": self.collect_address_details(shipper_address_id, is_send_shipper_number=True),
                    "ShipTo": {
                        "Name": recipient_address_id.name[:34] or "",
                        "AttentionName": picking.partner_id.parent_id and picking.partner_id.parent_id.name or picking.partner_id.name or "",
                        "TaxIdentificationNumber": picking.partner_id.vat or "",
                        "Phone": {
                            "Number": recipient_address_id.phone.replace(' ','')[:15] or ""
                        },
                        "EMailAddress": recipient_address_id.email,
                        "Address": {
                            "AddressLine": [receiver_street and receiver_street[:35] or "",
                                            receiver_street2 and receiver_street2[:35] or ""],
                            "City": receiver_city,
                            "StateProvinceCode": receiver_state,
                            "PostalCode": receiver_zip,
                            "CountryCode": receiver_country_code
                        },
                    },
                    # "ReferenceNumber": {
                    #     "Value": picking.name or ""
                    # },
                    "ShipFrom": self.collect_address_details(shipper_address_id),
                    "PaymentInformation": {
                        "ShipmentCharge": {
                            "Type": "01",
                            # ThirdParty payment
                        }
                    },
                    "Service": {
                        "Code": self.ups_service_type
                    },
                    # for US to canada
                    "InvoiceLineTotal": {
                        "CurrencyCode": '{}'.format(
                            self.company_id and self.company_id.currency_id and self.company_id.currency_id.name) or " ",
                        "MonetaryValue": str(total_ups_cod_amount)
                    },
                    "ShipmentServiceOptions": {},
                    "Package": packages
                },
                "LabelSpecification": {
                    "LabelImageFormat": {
                        "Code": str(self.ups_label_print_methods)
                    },
                    "LabelStockSize": {
                        "Height": '6',
                        "Width": '4'
                    }
                }
            }
        })

        if recipient_address_id.phone:
            receiver_phone_no = payload.get('ShipmentRequest').get('Shipment').get('ShipTo')
            receiver_phone_no.update({"Phone": {
                "Number": recipient_address_id.phone.replace(' ','')[:15] or ""
            }})

        # ups shipment indication type
        if self.ups_shipment_indication_type:
            shipment_indication_type = payload['ShipmentRequest']['Shipment']
            shipment_indication_type.update({
                "AlternateDeliveryAddress": {
                    "Name": ship_to_name,
                    "AttentionName": picking.partner_id.name or "",
                    "Address": {
                        "AddressLine": [receiver_street and receiver_street[:35] or "",
                                        receiver_street2 and receiver_street2[:35] or ""],
                        "City": receiver_city,
                        "StateProvinceCode": receiver_state,
                        "PostalCode": receiver_zip,
                        "CountryCode": receiver_country_code
                    },
                },
                "ShipmentIndicationType": [
                    {
                        "Code": self.ups_shipment_indication_type
                    }
                ],
            })

        # negotiated_Rate
        if self.negotiated_rate:
            negotiatedrate = payload.get('ShipmentRequest') and payload.get('ShipmentRequest').get('Shipment')
            negotiatedrate.update({"ShipmentRatingOptions": {"NegotiatedRatesIndicator": "ABR"}})

        # commercial invoice
        commercial_invoice_check = shipper_address_id.country_id.id != recipient_address_id.country_id.id
        if self.commercial_invoice and commercial_invoice_check:
            product_list = []
            mrp_module = self.env['ir.module.module'].search([('name', '=', 'mrp')])
            sale_line_added = []
            for rec in picking.move_ids:
                product_id = rec.product_id
                if picking.sale_id:
                    if mrp_module and mrp_module.state == 'installed':
                        if rec.bom_line_id and rec.bom_line_id.bom_id and rec.bom_line_id.bom_id.product_id:
                            product_id = rec.bom_line_id.bom_id.product_id
                            find_sale_line_id = picking.sale_id.order_line.filtered(lambda
                                                                                        x: x.product_id.id == product_id.id and rec.sale_line_id.id == x.id)
                            find_sale_line_id = find_sale_line_id[0]
                        elif rec.bom_line_id and rec.bom_line_id.bom_id.mapped(
                                'product_tmpl_id'):
                            product_tmpl_id = rec.bom_line_id.bom_id.product_tmpl_id
                            find_sale_line_id = picking.sale_id.order_line.filtered(lambda
                                                                                        x: x.product_id.product_tmpl_id.id == product_tmpl_id.id and rec.sale_line_id.id == x.id)
                            find_sale_line_id = find_sale_line_id and find_sale_line_id[0]
                        else:
                            find_sale_line_id = picking.sale_id.order_line.filtered(lambda
                                                                                        x: x.product_id.id == product_id.id and rec.sale_line_id.id == x.id)
                            find_sale_line_id = find_sale_line_id and find_sale_line_id[0]
                    else:
                        find_sale_line_id = picking.sale_id.order_line.filtered(
                            lambda
                                x: x.product_id.id == product_id.id and rec.sale_line_id.id == x.id)
                        find_sale_line_id = find_sale_line_id and find_sale_line_id[0]
                    if find_sale_line_id.id in sale_line_added:
                        continue
                    sale_line_added.append(find_sale_line_id.id)
                    _logger.info("Bulk Product : {}".format(product_id))
                    if not find_sale_line_id or not find_sale_line_id.product_uom_qty:
                        raise ValidationError("Proper data of sale order lines not found.")
                    single_unit_price = find_sale_line_id.price_total / find_sale_line_id.product_uom_qty
                    if mrp_module and mrp_module.state == 'installed':
                        if rec.bom_line_id and rec.bom_line_id.bom_id:
                            prodct_qty = rec.quantity
                        else:
                            prodct_qty = rec.quantity
                    else:
                        prodct_qty = rec.quantity
                else:
                    prodct_qty = rec.qty_done
                product_data = {
                    "Description": find_sale_line_id.product_id.name[:34] or "",
                    "Unit": {
                        "Number": "%s" % int(prodct_qty),
                        "Value": "%s" % (
                                round(single_unit_price, 3) or ""),
                        "UnitOfMeasurement": {
                            "Code": str(
                                "LB" if self.ups_weight_uom != "KGS" else "KG")
                        }
                    },
                    "CommodityCode": find_sale_line_id.product_id.hs_code or "",
                    "OriginCountryCode": "%s" % (
                            find_sale_line_id.product_id.country_of_origin.code or "")
                }
                product_list.append(product_data)
            commercial_invoice_data = payload.get('ShipmentRequest') and payload.get('ShipmentRequest').get(
                'Shipment') and payload.get('ShipmentRequest').get('Shipment').get('ShipmentServiceOptions')
            commercial_invoice_data.update({"InternationalForms": {
                "FormType": "01",
                "Product": product_list,
                "PurchaseOrderNumber": picking.sale_id and picking.sale_id.client_order_ref or "",
                "TermsOfShipment": picking.sale_id and picking.sale_id.incoterm and picking.sale_id.incoterm.code or "",
                "InvoiceNumber": picking.origin,
                "ReasonForExport": "SALE",
                "InvoiceDate": picking.scheduled_date.strftime("%Y%m%d"),
                "CurrencyCode": picking.company_id.currency_id.name or "",
                "Contacts": {
                    "SoldTo": {
                        "Name": recipient_address_id.name[:34] or "",
                        "AttentionName": picking.partner_id.parent_id and picking.partner_id.parent_id.name or picking.partner_id.name or "",
                        "TaxIdentificationNumber": recipient_address_id.vat or "",
                        "Phone": {
                            "Number": recipient_address_id.phone.replace(' ','')[:15] or ""
                        },
                        "Address": {
                            "AddressLine": [receiver_street and receiver_street[:35] or "",
                                            receiver_street2 and receiver_street2[:35] or ""],
                            "City": receiver_city,
                            "StateProvinceCode": receiver_state,
                            "CountryCode": receiver_country_code,
                        }
                    }
                }
            }})

            # Freight Charge
            is_delivery = picking.sale_id.order_line.filtered(lambda line: line.is_delivery)
            if is_delivery:
                commercial_invoice_data.get("InternationalForms").update({"FreightCharges": {
                    "MonetaryValue":    str(round(is_delivery.price_total,2))},})
        # cod for shipment level
        if self.ups_cod_parcel and self.ups_cod_service == "shipment_level":
            cod = payload.get('ShipmentRequest').get('Shipment').get('ShipmentServiceOptions')
            cod.update({"COD": {
                "CODFundsCode": self.ups_cod_fund_code,
                "CODAmount": {
                    "CurrencyCode": '{}'.format(
                        self.company_id and self.company_id.currency_id and self.company_id.currency_id.name) or " ",
                    "MonetaryValue": str(total_ups_cod_amount)
                }
            }})
        # signature
        if self.signature_required and not package_signature:
            if self.signature_required in ['2', '3']:
                signature_required = '1' if self.signature_required == '2' else '2'
                signature = payload.get('ShipmentRequest').get('Shipment').get('ShipmentServiceOptions')
                signature.update({
                        "DeliveryConfirmation": {
                            "DCISType": signature_required
                        }
                    })

        # saturday delivery
        if self.saturdaydelivery:
            saturday = payload.get('ShipmentRequest').get('Shipment').get('ShipmentServiceOptions')
            saturday.update({"SaturdayDeliveryIndicator": ""})

        # Notification
        if self.ups_notification_type:
            notification_type = payload.get('ShipmentRequest').get('Shipment').get('ShipmentServiceOptions')
            notification_type.update({"Notification": [{
                "NotificationCode": self.ups_notification_type,
                "EMail": {
                    "EMailAddress": recipient_address_id.email
                },
                "Locale": {
                    "Language": "ENG", # static
                    "Dialect": "US" # static
                }
            }]})

        # Location & Pickup(Pickup Point Functionality)
        if picking.sale_id.ups_shipping_location_id:
            Location_data = payload.get('ShipmentRequest').get('Shipment').get('ShipTo')
            Location_data.update({"LocationID": "{}".format(
                picking.sale_id.ups_shipping_location_id.location_id)})

        # ThirdParty payment
        if picking.sale_id.use_ups_third_party_account:
            thirdparty_payment = payload.get('ShipmentRequest').get('Shipment').get('PaymentInformation').get(
                'ShipmentCharge')
            thirdparty_payment.update({"BillThirdParty": {
                "AccountNumber": account_number,
                "Address": {
                    "PostalCode": party_zip,
                    "CountryCode": party_country
                }
            }})
        else:
            thirdparty_payment = payload.get('ShipmentRequest').get('Shipment').get('PaymentInformation').get(
                'ShipmentCharge')
            thirdparty_payment.update({"BillShipper": {
                "AccountNumber": company_id.ups_shipper_number
            }})
            # peparless invoice
        if picking.document_id:
            _logger.info(">>>>>>> Peparless Invoice:::: %s" % payload.get('ShipmentRequest').get('Shipment').get('ShipmentServiceOptions'))
            paperless_invoice = payload.get('ShipmentRequest').get('Shipment').get('ShipmentServiceOptions')
            paperless_invoice.update({"InternationalForms": {
                "FormType": "07",
                "UserCreatedForm": {
                    "DocumentID": picking.document_id
                }
            }})

        try:
            header = {'Authorization': "Bearer {}".format(company_id.ups_api_token),
                      'Content-Type': 'application/json', }
            api_url = "{}/api/shipments/v1/ship".format(company_id.ups_api_url)
            request_type = "POST"
            response_status, response_data = self.ups_provider_create_shipment(request_type, api_url,
                                                                               json.dumps(payload), header)
            if response_status and response_data.get('ShipmentResponse').get('ShipmentResults').get(
                    'ShipmentIdentificationNumber'):
                tracking_number = response_data.get('ShipmentResponse').get('ShipmentResults').get(
                    'ShipmentIdentificationNumber')
                lable_image = response_data.get('ShipmentResponse').get('ShipmentResults').get('PackageResults')
                if lable_image:
                    if isinstance(lable_image, dict):
                        lable_image = [lable_image]
                    label_datas = []
                    if self.ups_label_print_methods == 'GIF':
                        for detail in lable_image:
                            binary_data = detail.get('ShippingLabel').get('GraphicImage')
                            label_binary_data = binascii.a2b_base64(str(binary_data))
                            image_string = io.BytesIO(label_binary_data)
                            im = Image.open(image_string)
                            label_result = io.BytesIO()
                            im.save(label_result, 'pdf')
                            label_binary_data = label_result.getvalue()
                            label_datas.append(label_binary_data)
                        attachments = [('LabelUPS.pdf',
                                        pdf.merge_pdf([pl for pl in label_datas]))]
                    else:
                        for detail in lable_image:
                            binary_data = detail.get('ShippingLabel').get('GraphicImage')
                            label_binary_data = binascii.a2b_base64(str(binary_data))
                            label_datas.append(label_binary_data)
                        merged_zpl = b''.join(label_datas)
                        attachments = [('LabelUPS.zpl', merged_zpl)]

                    logmessage = (_("Shipment created!<br/> <b>Shipment Tracking Number : </b>%s") % (tracking_number))
                    picking.message_post(body=tools.html_sanitize(logmessage), attachments=attachments)

                    # Commercial Invoice
                    commercial_invoice_check = shipper_address_id.country_id.id != recipient_address_id.country_id.id
                    if self.commercial_invoice and commercial_invoice_check:
                        if response_status and response_data.get('ShipmentResponse').get('ShipmentResults').get(
                                'Form'):
                            commercial_data_pdf = response_data.get('ShipmentResponse').get('ShipmentResults').get(
                                'Form').get('Image').get('GraphicImage')
                            invoice_label_binary_data = binascii.a2b_base64(str(commercial_data_pdf))
                            message = (_("Commercial Invoice!<br/> <b>Shipment Tracking Number : </b>%s") % (
                                tracking_number))
                            picking.message_post(body=tools.html_sanitize(message), attachments=[
                                ('Commercial Invoice-%s.%s' % (tracking_number, "pdf"), invoice_label_binary_data)])

                if self.return_labels and tracking_number:
                    api_url = "{}/api/labels/v1/recovery".format(company_id.ups_api_url)

                    payload = json.dumps({
                        "LabelRecoveryRequest": {
                            "TrackingNumber": tracking_number
                        }
                    })
                    return_response_status, return_response_data = self.ups_provider_create_shipment(request_type, api_url,
                                                                                       payload, header)
                    if return_response_status:
                        return_label_data = return_response_data.get("LabelRecoveryResponse").get("LabelResults").get(
                            "LabelImage").get("GraphicImage")
                        return_label = binascii.a2b_base64(str(return_label_data))
                        message = (_("Return Label!<br/> <b>Shipment Tracking Number : </b>%s") % (
                            tracking_number))
                        picking.message_post(body=tools.html_sanitize(message), attachments=[
                            ('Return Label-%s.%s' % (tracking_number, "pdf"), return_label)])
                    else:
                        message = return_response_data
                        picking.message_post(body=(message))

                rate = response_data.get('ShipmentResponse') and response_data.get('ShipmentResponse').get(
                    'ShipmentResults') and response_data.get('ShipmentResponse').get('ShipmentResults').get(
                    'NegotiatedRateCharges') and response_data.get('ShipmentResponse').get('ShipmentResults').get(
                    'NegotiatedRateCharges').get('TotalCharge') and response_data.get('ShipmentResponse').get(
                    'ShipmentResults').get('NegotiatedRateCharges').get('TotalCharge').get(
                    'MonetaryValue') or response_data.get('ShipmentResponse') and response_data.get(
                    'ShipmentResponse').get('ShipmentResults') and response_data.get('ShipmentResponse').get(
                    'ShipmentResults').get('ShipmentCharges') and response_data.get('ShipmentResponse').get(
                    'ShipmentResults').get('ShipmentCharges').get('TotalCharges') and response_data.get(
                    'ShipmentResponse').get('ShipmentResults').get('ShipmentCharges').get('TotalCharges').get(
                    'MonetaryValue') or 0.0
                shipping_data = {'exact_price': float(rate), 'tracking_number': tracking_number}
                shipping_data = [shipping_data]
                return shipping_data
            else:
                raise ValidationError(response_data)
        except Exception as e:
            raise ValidationError(e)

    """ Paperless invoice """

    def ups_paperless_invoice_provider(self, picking):
        pdf_file = self.env.ref('sale.action_report_saleorder')._render_qweb_pdf(
            picking.sale_id.ids)
        pdf_file = bytes(pdf_file[0])
        pdf_file = base64.b64encode(pdf_file).decode('utf-8')
        request_data = ({
            "UploadRequest": {
                "Request": {
                    "TransactionReference": {
                        "CustomerContext": ""
                    }
                },
                "ShipperNumber": self.company_id.ups_shipper_number,
                "UserCreatedForm": {
                    "UserCreatedFormFileName": "Paperless.pdf",
                    "UserCreatedFormFileFormat": "txt",
                    "UserCreatedFormDocumentType": "013",
                    "UserCreatedFormFile": pdf_file
                }
            }
        })

        headers = {
            'ShipperNumber': self.company_id.ups_shipper_number,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': "Bearer {}".format(self.company_id.ups_api_token),
        }
        api_url = "{}/api/paperlessdocuments/v1/upload".format(self.company_id.ups_api_url)
        try:
            _logger.info("API Request Data {}".format(request_data))
            response = requests.request("POST", api_url, headers=headers, data=json.dumps(request_data))
            if response.status_code in [200, 201]:
                invoice_resonce = response.json()
                picking.document_id = invoice_resonce.get('UploadResponse') and invoice_resonce.get(
                    'UploadResponse').get('FormsHistoryDocumentID') and invoice_resonce.get('UploadResponse').get(
                    'FormsHistoryDocumentID').get(
                    'DocumentID')
                response = response.content if request_data else response.json()
                _logger.info("API Response Data {}".format(response))
                return {
                    'effect': {
                        'fadeout': 'slow',
                        'message': "Yeah! UPS Token Retrieved successfully!!",
                        'img_url': '/web/static/img/smile.svg',
                        'type': 'rainbow_man',
                    }
                }
            else:
                errors_message = "Paperless Invoice: {}".format(
                    json.loads(response.text).get('response') and json.loads(response.text).get(
                        'response').get('errors') and json.loads(response.text).get('response').get('errors')[
                        0].get(
                        'message'))
                raise ValidationError(errors_message)
        except Exception as e:
            raise ValidationError(e)

    def ups_provider_cancel_shipment(self, picking):
        """this method is used for cancel the shipment if shipment will not export as order"""
        shipping_id = picking.carrier_tracking_ref
        if shipping_id:
            url = "{0}/api/shipments/v1/void/cancel/{1}".format(self.company_id.ups_api_url,
                                                                picking.carrier_tracking_ref)
            payload = {}
            headers = {'Accept': 'application/json',
                       'Authorization': "Bearer {}".format(self.company_id.ups_api_token)}
            try:
                cancel_response = requests.request("DELETE", url, headers=headers, data=payload)
                if cancel_response.status_code == 200:
                    _logger.info("Cancel UPS Shipment Successfully.")
                else:
                    raise ValidationError(cancel_response)
            except Exception:
                cancel_response = json.loads(cancel_response.text)
                error = cancel_response.get('response').get('errors')[0].get('message')
                raise ValidationError(error)
        else:
            raise ValidationError(_("Shipment identification number not available!"))

    def ups_provider_get_tracking_link(self, pickings):
        return "https://wwwapps.ups.com/WebTracking/track?trackNums=%s" % (pickings.carrier_tracking_ref)
