import binascii
import logging
import datetime
from odoo.exceptions import Warning, ValidationError
from odoo import models, fields, api, _
from odoo.addons.fedex_shipping_odoo_integration.fedex.base_service import FedexError, FedexFailure
from odoo.addons.fedex_shipping_odoo_integration.fedex.tools.conversion import basic_sobject_to_dict
from odoo.addons.fedex_shipping_odoo_integration.fedex.services.rate_service import FedexRateServiceRequest
from odoo.addons.fedex_shipping_odoo_integration.fedex.services.ship_service import FedexDeleteShipmentRequest
from odoo.addons.fedex_shipping_odoo_integration.fedex.services.ship_service import FedexProcessShipmentRequest
from odoo.addons.fedex_shipping_odoo_integration.fedex.services.address_validation_service import \
    FedexAddressValidationRequest

_logger = logging.getLogger(__name__)


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(selection_add=[('fedex_shipping_provider', 'Fedex')])
    add_custom_margin = fields.Float(string="Margin", help="Add This Margin In Rate When Rate Comes From FedEx.",
                                     default=0.0)
    fedex_service_type = fields.Selection(
        [('EUROPE_FIRST_INTERNATIONAL_PRIORITY', 'Europe First International Priority'),
         ('SMART_POST', 'Smart Post'),  # When Call the service given the error "Customer not eligible for service"
         ('FEDEX_GROUND', 'Fedex Ground'),  # When Call the service given the error "Customer not eligible for service"
         ('FEDEX_DISTANCE_DEFERRED', 'Fedex Distance Deferred'),
         # for domestic UK pickup  Error : Customer is eligible.
         ('FEDEX_NEXT_DAY_AFTERNOON', 'Fedex Next Day Afternoon'),  # for domestic UK pickup
         ('FEDEX_NEXT_DAY_EARLY_MORNING', 'Fedex Next Day Early Morning'),  # for domestic UK pickup
         ('FEDEX_NEXT_DAY_END_OF_DAY', 'Fedex Next Day End of Day'),  # for domestic UK pickup
         ('FEDEX_NEXT_DAY_FREIGHT', 'Fedex Next Day Freight'),  # for domestic UK pickup
         ('FEDEX_NEXT_DAY_MID_MORNING', 'Fedex Next Day Mid Morning'),  # for domestic UK pickup
         ('GROUND_HOME_DELIVERY', 'Ground Home Delivery'),
         # To Address Use: 33122 Florida Doral US. From Add use: 33122 Florida Doral US and Package type box is your_packaging.
         ('INTERNATIONAL_ECONOMY', 'International Economy'),
         # To Address Use: 33122 Florida Doral US. From Add use: 12277 Germany Berlin Penna.
         ('INTERNATIONAL_FIRST', 'International First'),
         # To Address Use: 33122 Florida Doral US. From Add use: 12277 Germany Berlin Penna.
         ('INTERNATIONAL_PRIORITY', 'International Priority'),
         # To Address Use: 33122 Florida Doral US. From Add use: 73377 "Le Bourget du Lac" France
         ('FIRST_OVERNIGHT', 'First Overnight'),  # for US
         ('PRIORITY_OVERNIGHT', 'Priority Overnight'),  # for US
         ('FEDEX_2_DAY', 'Fedex 2 Day'),  # for US Use: 33122 Florida Doral
         ('FEDEX_2_DAY_AM', 'Fedex 2 Day AM'),  # for US Use: 33122 Florida Doral
         ('FEDEX_EXPRESS_SAVER', 'Fedex Express Saver'),  # for US Use: 33122 Florida Doral
         ('STANDARD_OVERNIGHT', 'Standard Overnight')  # for US Use: 33122 Florida Doral
         ], string="Service Type", help="Shipping Services those are accepted by Fedex")

    fedex_droppoff_type = fields.Selection([('BUSINESS_SERVICE_CENTER', 'Business Service Center'),
                                            ('DROP_BOX', 'Drop Box'),
                                            ('REGULAR_PICKUP', 'Regular Pickup'),
                                            ('REQUEST_COURIER', 'Request Courier'),
                                            ('STATION', 'Station')],
                                           string="Drop-off Type",
                                           default='REGULAR_PICKUP',
                                           help="Identifies the method by which the package is to be tendered to FedEx.")
    fedex_default_product_packaging_id = fields.Many2one('product.packaging', string="Default Package Type")
    fedex_weight_uom = fields.Selection([('LB', 'LB'),
                                         ('KG', 'KG')], default='LB', string="Weight UoM",
                                        help="Weight UoM of the Shipment")
    fedex_collection_type = fields.Selection([('ANY', 'ANY'),
                                              ('CASH', 'CASH'),
                                              ('COMPANY_CHECK', 'COMPANY_CHECK'),
                                              ('GUARANTEED_FUNDS', 'GUARANTEED_FUNDS'),
                                              ('PERSONAL_CHECK', 'PERSONAL_CHECK'),
                                              ], default='ANY', string="FedEx Collection Type",
                                             help="FedEx Collection Type")

    # fedex_payment_type = fields.Selection([('SENDER', 'SENDER'),
    #                                        ('RECIPIENT', 'RECIPIENT'),
    #                                        ('THIRD_PARTY', 'THIRD_PARTY')], default='SENDER',
    #                                       string="FedEx Payment Type",
    #                                       help="FedEx Payment Type")

    fedex_shipping_label_stock_type = fields.Selection([
        # These values display a thermal format label
        ('PAPER_4X6', 'Paper 4X6 '),
        ('PAPER_4X8', 'Paper 4X8'),
        ('PAPER_4X9', 'Paper 4X9'),

        # These values display a plain paper format shipping label
        ('PAPER_7X4.75', 'Paper 7X4.75'),
        ('PAPER_8.5X11_BOTTOM_HALF_LABEL', 'Paper 8.5X11 Bottom Half Label'),
        ('PAPER_8.5X11_TOP_HALF_LABEL', 'Paper 8.5X11 Top Half Label'),
        ('PAPER_LETTER', 'Paper Letter'),

        # These values for Stock Type label
        ('STOCK_4X6', 'Stock 4X6'),
        ('STOCK_4X6.75_LEADING_DOC_TAB', 'Stock 4X6.75 Leading Doc Tab'),
        ('STOCK_4X6.75_TRAILING_DOC_TAB', 'Stock 4X6.75 Trailing Doc Tab'),
        ('STOCK_4X8', 'Stock 4X8'),
        ('STOCK_4X9_LEADING_DOC_TAB', 'Stock 4X9 Leading Doc Tab'),
        ('STOCK_4X9_TRAILING_DOC_TAB', 'Stock 4X9 Trailing Doc Tab')], string="Label Stock Type",
        help="Specifies the type of paper (stock) on which a document will be printed.")
    fedex_shipping_label_file_type = fields.Selection([('DPL', 'DPL'),
                                                       ('EPL2', 'EPL2'),
                                                       ('PDF', 'PDF'),
                                                       ('PNG', 'PNG'),
                                                       ('ZPLII', 'ZPLII')], string="Label File Type")
    fedex_onerate = fields.Boolean("Want To Use FedEx OneRate Service?", default=False)
    fedex_third_party_account_number = fields.Char(copy=False, string='FexEx Third-Party Account Number',
                                                   help="Please Enter the Third Party account number")
    is_cod = fields.Boolean('COD')

    @api.onchange('fedex_default_product_packaging_id', 'fedex_service_type')
    def fedex_onchange_service_and_package(self):
        self.fedex_onerate = False

    def do_address_validation(self, address):
        """
        Call to get the validated address from Fedex or Classification : Can be used to determine the address classification to figure out if Residential fee should apply.
        values are return in classification : MIXED, RESIDENTIAL, UNKNOWN, BUSINESS
        use address validation services, client need to request fedex to enable this service for his account.
        By default, The service is disable and you will receive authentication failed.
        """
        try:
            FedexConfig = self.company_id.get_fedex_api_object()
            avs_request = FedexAddressValidationRequest(FedexConfig)
            address_to_validate = avs_request.create_wsdl_object_of_type('AddressToValidate')
            street_lines = []
            if address.street:
                street_lines.append(address.street)
            if address.street2:
                street_lines.append(address.street2)
            address_to_validate.Address.StreetLines = street_lines
            address_to_validate.Address.City = address.city
            if address.state_id:
                address_to_validate.Address.StateOrProvinceCode = address.state_id.code
            address_to_validate.Address.PostalCode = address.zip
            if address.country_id:
                address_to_validate.Address.CountryCode = address.country_id.code
            avs_request.add_address(address_to_validate)
            avs_request.send_request()
            response = basic_sobject_to_dict(avs_request.response)
            if response.get('AddressResults'):
                return response['AddressResults'][0]  # Classification
        except FedexError as ERROR:
            raise ValidationError(ERROR.value)
        except FedexFailure as ERROR:
            raise ValidationError(ERROR.value)
        except Exception as e:
            raise ValidationError(e)

    def prepare_shipment_request(self, instance, request_obj, shipper, recipient, package_type, order):
        self.ensure_one()
        # If you wish to have transit data returned with your request you
        request_obj.ReturnTransitAndCommit = True
        request_obj.RequestedShipment.ShipTimestamp = datetime.datetime.now().replace(microsecond=0).isoformat()
        request_obj.RequestedShipment.DropoffType = self.fedex_droppoff_type
        request_obj.RequestedShipment.ServiceType = self.fedex_service_type
        request_obj.RequestedShipment.PackagingType = package_type

        # Shipper's address
        residential = True
        if instance.use_address_validation_service:
            validated_address = self.do_address_validation(shipper)
            residential = validated_address.get('Classification') != 'BUSINESS'

        request_obj.RequestedShipment.Shipper.Contact.PersonName = shipper.name if not shipper.is_company else ''
        request_obj.RequestedShipment.Shipper.Contact.CompanyName = shipper.name if shipper.is_company else ''
        request_obj.RequestedShipment.Shipper.Contact.PhoneNumber = shipper.phone
        request_obj.RequestedShipment.Shipper.Address.StreetLines = shipper.street and shipper.street2 and [
            shipper.street, shipper.street2] or [shipper.street]
        request_obj.RequestedShipment.Shipper.Address.City = shipper.city or None
        request_obj.RequestedShipment.Shipper.Address.StateOrProvinceCode = shipper.state_id and shipper.state_id.code or None
        request_obj.RequestedShipment.Shipper.Address.PostalCode = shipper.zip
        request_obj.RequestedShipment.Shipper.Address.CountryCode = shipper.country_id.code
        request_obj.RequestedShipment.Shipper.Address.Residential = residential

        # Recipient address
        residential = False
        if instance.use_address_validation_service:
            validated_address = self.do_address_validation(recipient)
            residential = validated_address.get('Classification') != 'BUSINESS'

        request_obj.RequestedShipment.Recipient.Contact.PersonName = recipient.name if not recipient.is_company else ''
        request_obj.RequestedShipment.Recipient.Contact.CompanyName = recipient.name if recipient.is_company else ''
        request_obj.RequestedShipment.Recipient.Contact.PhoneNumber = recipient.mobile or recipient.phone
        request_obj.RequestedShipment.Recipient.Address.StreetLines = recipient.street and recipient.street2 and [
            recipient.street, recipient.street2] or [recipient.street]
        request_obj.RequestedShipment.Recipient.Address.City = recipient.city
        request_obj.RequestedShipment.Recipient.Address.StateOrProvinceCode = recipient.state_id and recipient.state_id.code or ''
        request_obj.RequestedShipment.Recipient.Address.PostalCode = recipient.zip
        request_obj.RequestedShipment.Recipient.Address.CountryCode = recipient.country_id.code
        request_obj.RequestedShipment.Recipient.Address.Residential = residential
        # include estimated duties and taxes in rate quote, can be ALL or NONE
        request_obj.RequestedShipment.EdtRequestType = 'NONE'

        request_obj.RequestedShipment.ShippingChargesPayment.Payor.ResponsibleParty.AccountNumber = order.fedex_third_party_account_number_sale_order if order.fedex_third_party_account_number_sale_order  else instance.fedex_account_number
        request_obj.RequestedShipment.ShippingChargesPayment.PaymentType = "RECIPIENT" if order.fedex_third_party_account_number_sale_order else "SENDER"
        return request_obj

    def manage_fedex_packages(self, rate_request, weight, number=1):
        package_weight = rate_request.create_wsdl_object_of_type('Weight')
        package_weight.Value = weight
        package_weight.Units = self.fedex_weight_uom
        package = rate_request.create_wsdl_object_of_type('RequestedPackageLineItem')
        package.Weight = package_weight
        if self.fedex_default_product_packaging_id.shipper_package_code == 'YOUR_PACKAGING':
            package.Dimensions.Length = self.fedex_default_product_packaging_id.length
            package.Dimensions.Width = self.fedex_default_product_packaging_id.width
            package.Dimensions.Height = self.fedex_default_product_packaging_id.height
            package.Dimensions.Units = 'IN' if self.fedex_weight_uom == 'LB' else 'CM'
        package.PhysicalPackaging = 'BOX'
        package.GroupPackageCount = 1
        if number:
            package.SequenceNumber = number
        return package

    def add_fedex_package(self, ship_request, weight, package_count, number=1, master_tracking_id=False,package_id=False):
        package_weight = ship_request.create_wsdl_object_of_type('Weight')
        package_weight.Value = weight
        package_weight.Units = self.fedex_weight_uom
        package = ship_request.create_wsdl_object_of_type('RequestedPackageLineItem')
        package.Weight = package_weight
        if self.fedex_default_product_packaging_id.shipper_package_code == 'YOUR_PACKAGING':
            package.Dimensions.Length = package_id and package_id.packaging_id.length if package_id and package_id.packaging_id.length else self.fedex_default_product_packaging_id.length
            package.Dimensions.Width = package_id and package_id.packaging_id.width if package_id and package_id.packaging_id.width else self.fedex_default_product_packaging_id.width
            package.Dimensions.Height =package_id and package_id.packaging_id.height if package_id and package_id.packaging_id.height else self.fedex_default_product_packaging_id.height
            package.Dimensions.Units = 'IN' if self.fedex_weight_uom == 'LB' else 'CM'
        package.PhysicalPackaging = 'BOX'
        if number:
            package.SequenceNumber = number
        ship_request.RequestedShipment.RequestedPackageLineItems = package
        ship_request.RequestedShipment.TotalWeight.Value = weight
        ship_request.RequestedShipment.PackageCount = package_count
        if master_tracking_id:
            ship_request.RequestedShipment.MasterTrackingId.TrackingIdType = 'FEDEX'
            ship_request.RequestedShipment.MasterTrackingId.TrackingNumber = master_tracking_id
        return ship_request

    #
    # @api.model
    # def (self, picking, ship_request, weight, package_count, number=1, master_tracking_id=False,package=False):
    #     package_weight = ship_request.create_wsdl_object_of_type('Weight')
    #     package_weight.Value = weight
    #     package_weight.Units = self.fedex_weight_uom
    #     package_request = ship_request.create_wsdl_object_of_type('RequestedPackageLineItem')
    #     package_request.Weight = package_weight
    #     if self.fedex_default_product_packaging_id.shipper_package_code == 'YOUR_PACKAGING' :
    #         package=package if package else self.fedex_default_product_packaging_id
    #         package_request.Dimensions.Length = package and package.length
    #         package_request.Dimensions.Width = package and package.width
    #         package_request.Dimensions.Height = package and package.height
    #         package_request.Dimensions.Units = 'IN' if self.fedex_weight_uom == 'LB' else 'CM'
    #     package_request.PhysicalPackaging = 'BOX'
    #     if number :
    #         package_request.SequenceNumber = number
    #
    #     CustomerReference = []
    #     CustomerReference1 = ship_request.create_wsdl_object_of_type('CustomerReference')
    #     CustomerReference1.CustomerReferenceType = "P_O_NUMBER"  #customer reference
    #     CustomerReference1.Value = (picking.sale_id and picking.sale_id.client_order_ref) or ""
    #
    #     CustomerReference.append(CustomerReference1)
    #
    #     CustomerReference2 = ship_request.create_wsdl_object_of_type('CustomerReference')
    #     CustomerReference2.CustomerReferenceType = "INVOICE_NUMBER"
    #     CustomerReference2.Value = picking.name #picking name
    #
    #     CustomerReference.append(CustomerReference2)
    #
    #     package_request.CustomerReferences = CustomerReference
    #
    #     ship_request.RequestedShipment.RequestedPackageLineItems = package_request
    #     ship_request.RequestedShipment.TotalWeight.Value = weight
    #     ship_request.RequestedShipment.PackageCount = package_count
    #     if master_tracking_id :
    #         ship_request.RequestedShipment.MasterTrackingId.TrackingIdType = 'FEDEX'
    #         ship_request.RequestedShipment.MasterTrackingId.TrackingNumber = master_tracking_id
    #     if package and self.fedex_service_type in ['INTERNATIONAL_ECONOMY', 'INTERNATIONAL_FIRST', 'INTERNATIONAL_PRIORITY'] or (picking.partner_id.country_id.code == 'IN' and picking.picking_type_id.warehouse_id.partner_id.country_id.code == 'IN'):
    #         order = picking.sale_id
    #         company = order.company_id or picking.company_id or self.env.user.company_id
    #         order_currency = picking.sale_id.currency_id or picking.company_id.currency_id
    #         commodity_country_of_manufacture = picking.picking_type_id.warehouse_id.partner_id.country_id.code
    #         commodity_weight_units = self.fedex_weight_uom
    #         total_commodities_amount = 0.0
    #         for operation in picking.move_line_ids:
    #             commodity_amount = order_currency._convert(operation.product_id.list_price, order_currency, company, order.date_order or fields.Date.today())
    #             total_commodities_amount +=(commodity_amount * operation.quantity)
    #             Commodity = ship_request.create_wsdl_object_of_type('Commodity')
    #             Commodity.UnitPrice.Currency = order_currency.name
    #             Commodity.UnitPrice.Amount = commodity_amount
    #             Commodity.NumberOfPieces = '1'
    #             Commodity.CountryOfManufacture = commodity_country_of_manufacture
    #             Commodity.Weight.Units = commodity_weight_units
    #             Commodity.Weight.Value = weight
    #             Commodity.Description = operation.product_id.name
    #             Commodity.Quantity = operation.quantity
    #             Commodity.QuantityUnits = 'EA'
    #             ship_request.RequestedShipment.CustomsClearanceDetail.Commodities.append(Commodity)
    #         ship_request.RequestedShipment.CustomsClearanceDetail.DutiesPayment.PaymentType = 'SENDER'
    #         ship_request.RequestedShipment.CustomsClearanceDetail.DutiesPayment.Payor.ResponsibleParty.AccountNumber = self.company_id and self.company_id.fedex_account_number
    #         ship_request.RequestedShipment.CustomsClearanceDetail.DutiesPayment.Payor.ResponsibleParty.Address.CountryCode = picking.picking_type_id.warehouse_id.partner_id.country_id.code
    #         ship_request.RequestedShipment.CustomsClearanceDetail.CustomsValue.Amount = total_commodities_amount
    #         ship_request.RequestedShipment.CustomsClearanceDetail.CustomsValue.Currency = picking.sale_id.currency_id.name or picking.company_id.currency_id.name
    #     return ship_request

    def fedex_shipping_provider_rate_shipment(self, orders):
        res = []
        shipping_charge = 0.0
        for order in orders:
            order_lines_without_weight = order.order_line.filtered(
                lambda line_item: not line_item.product_id.type in ['service',
                                                                    'digital'] and not line_item.product_id.weight and not line_item.is_delivery)
            for order_line in order_lines_without_weight:
                raise ValidationError("Please define weight in product : \n %s" % (order_line.product_id.name))

            # Shipper and Recipient Address
            shipper_address = order.warehouse_id.partner_id
            recipient_address = order.partner_shipping_id
            shipping_credential = self.company_id

            # check sender Address
            if not shipper_address.zip or not shipper_address.city or not shipper_address.country_id:
                raise ValidationError("Please Define Proper Sender Address!")

            # check Receiver Address
            if not recipient_address.zip or not recipient_address.city or not recipient_address.country_id:
                raise ValidationError("Please Define Proper Recipient Address!")

            total_weight = sum([(line.product_id.weight * line.product_uom_qty) for line in order.order_line]) or 0.0
            total_weight = self.company_id.weight_convertion(self.fedex_weight_uom, total_weight)
            max_weight = self.company_id.weight_convertion(self.fedex_weight_uom,
                                                           self.fedex_default_product_packaging_id.max_weight)
            try:
                # This is the object that will be handling our request.
                FedexConfig = self.company_id.get_fedex_api_object(self.prod_environment)
                rate_request = FedexRateServiceRequest(FedexConfig)
                package_type = self.fedex_default_product_packaging_id.shipper_package_code
                rate_request = self.prepare_shipment_request(shipping_credential, rate_request, shipper_address,
                                                             recipient_address, package_type, order)
                rate_request.RequestedShipment.PreferredCurrency = order.currency_id.name
                if max_weight and total_weight > max_weight:
                    total_package = int(total_weight / max_weight)
                    last_package_weight = total_weight % max_weight

                    for index in range(1, total_package + 1):
                        package = self.manage_fedex_packages(rate_request, max_weight, index)
                        rate_request.add_package(package)
                    if last_package_weight:
                        index = total_package + 1
                        package = self.manage_fedex_packages(rate_request, last_package_weight, index)
                        rate_request.add_package(package)
                #                         rate_request.RequestedShipment.RequestedPackageLineItems.append(package)
                else:
                    total_package = 1
                    package = self.manage_fedex_packages(rate_request, total_weight)
                    rate_request.add_package(package)
                #                 rate_request.RequestedShipment.TotalWeight.Value = total_weight
                #                 rate_request.RequestedShipment.PackageCount = total_package
                if self.fedex_onerate:
                    rate_request.RequestedShipment.SpecialServicesRequested.SpecialServiceTypes = ['FEDEX_ONE_RATE']
                if self.is_cod and not order.fedex_third_party_account_number_sale_order:
                    #rate_request.RequestedShipment.SpecialServicesRequested.SpecialServiceTypes = ['COD']
                    cod_vals = {'Amount': order.amount_total,
                                'Currency': order.company_id.currency_id.name}
                    rate_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodCollectionAmount = cod_vals
                    rate_request.RequestedShipment.SpecialServicesRequested.CodDetail.CollectionType.value = "%s" % (
                        self.fedex_collection_type)

                    rate_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Contact.PersonName = shipper_address.name if not shipper_address.is_company else ''
                    rate_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Contact.CompanyName = shipper_address.name if shipper_address.is_company else ''
                    rate_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Contact.PhoneNumber = shipper_address.phone
                    rate_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Address.StreetLines = shipper_address.street and shipper_address.street2 and [
                        shipper_address.street, shipper_address.street2] or [shipper_address.street]
                    rate_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Address.City = shipper_address.city or None
                    rate_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Address.StateOrProvinceCode = shipper_address.state_id and shipper_address.state_id.code or None
                    rate_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Address.PostalCode = shipper_address.zip
                    rate_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Address.CountryCode = shipper_address.country_id.code

                rate_request.send_request()
            except FedexError as ERROR:
                raise ValidationError(ERROR.value)
                # raise ValidationError(ERROR.value)
            except FedexFailure as ERROR:
                raise ValidationError(ERROR.value)
                # raise ValidationError(ERROR.value)
            except Exception as e:
                raise ValidationError(e)
                # raise ValidationError(e)
            for shipping_service in rate_request.response.RateReplyDetails:
                for rate_info in shipping_service.RatedShipmentDetails:
                    shipping_charge = float(rate_info.ShipmentRateDetail.TotalNetFedExCharge.Amount)
                    shipping_charge_currency = rate_info.ShipmentRateDetail.TotalNetFedExCharge.Currency
                    if order.currency_id.name != rate_info.ShipmentRateDetail.TotalNetFedExCharge.Currency:
                        rate_currency = self.env['res.currency'].search([('name', '=', shipping_charge_currency)],
                                                                        limit=1)
                        if rate_currency:
                            shipping_charge = rate_currency.compute(float(shipping_charge), order.currency_id)
        return {'success': True, 'price': float(shipping_charge) + self.add_custom_margin, 'error_message': False,
                'warning_message': False}

    def get_fedex_tracking_and_label(self, ship_request,is_cod=False):
        self.ensure_one()
        CompletedPackageDetails = ship_request.response.CompletedShipmentDetail.CompletedPackageDetails[0]
        shipping_charge = 0.0
        if hasattr(CompletedPackageDetails, 'PackageRating'):
            shipping_charge = CompletedPackageDetails.PackageRating.PackageRateDetails[0].NetCharge.Amount
        else:
            _logger.warn('Unable to get shipping rate!')
        tracking_number = CompletedPackageDetails.TrackingIds[0].TrackingNumber
        ascii_label_data = ship_request.response.CompletedShipmentDetail.CompletedPackageDetails[0].Label.Parts[0].Image
        cod_details = False
        cod_error_message = False
        try:
            if is_cod:
                cod_details = ship_request.response.CompletedShipmentDetail.AssociatedShipments[0] and \
                              ship_request.response.CompletedShipmentDetail.AssociatedShipments[0].Label and \
                              ship_request.response.CompletedShipmentDetail.AssociatedShipments[0].Label.Parts[0] and \
                              ship_request.response.CompletedShipmentDetail.AssociatedShipments[0].Label.Parts[
                                  0].Image or False
                if cod_details:
                    cod_details = binascii.a2b_base64(cod_details)
        except Exception as e:
            cod_error_message = e
        label_binary_data = binascii.a2b_base64(ascii_label_data)
        return shipping_charge, tracking_number, label_binary_data, cod_details, cod_error_message

    # require changes in this module

    def fedex_shipping_provider_send_shipping(self, pickings):
        res = []
        fedex_master_tracking_id = False
        for picking in pickings:
            if not (picking.sale_id and picking.sale_id.fedex_bill_by_third_party_sale_order):
                picking.get_fedex_rate()
            exact_price = 0.0
            traking_number = []
            attachments = []
            total_bulk_weight = self.company_id.weight_convertion(self.fedex_weight_uom, picking.weight_bulk)
            package_count = len(picking.package_ids)
            if total_bulk_weight:
                package_count += 1
            shipping_credential = self.company_id

            # if not picking.package_ids:
            #     raise ValidationError("Package details are not available!")
            if not self._context.get('use_fedex_return', False) and picking.picking_type_code == "incoming":
                shipping_data = {
                    'exact_price': picking.carrier_price,
                    'tracking_number': picking.carrier_tracking_ref}
                return [shipping_data]

            if picking.picking_type_code == "incoming":
                shipper_address = picking.partner_id
                recipient_address = picking.picking_type_id.warehouse_id.partner_id
            else:
                recipient_address = picking.partner_id
                shipper_address = picking.picking_type_id.warehouse_id.partner_id
            try:
                FedexConfig = self.company_id.get_fedex_api_object(self.prod_environment)
                ship_request = FedexProcessShipmentRequest(FedexConfig)

                # checking for Identical packages in same shipment.
                # picking.check_packages_are_identical()

                package_type = self.fedex_default_product_packaging_id.shipper_package_code
                ship_request = self.prepare_shipment_request(shipping_credential, ship_request, shipper_address,
                                                             recipient_address, package_type, picking.sale_id)

                # Supported LabelFormatType by fedex
                # COMMON2D, FEDEX_FREIGHT_STRAIGHT_BILL_OF_LADING, LABEL_DATA_ONLY, VICS_BILL_OF_LADING
                ship_request.RequestedShipment.LabelSpecification.LabelFormatType = 'COMMON2D'
                ship_request.RequestedShipment.LabelSpecification.ImageType = self.fedex_shipping_label_file_type
                ship_request.RequestedShipment.LabelSpecification.LabelStockType = self.fedex_shipping_label_stock_type
                #                 if self.fedex_service_type in ['INTERNATIONAL_ECONOMY', 'INTERNATIONAL_FIRST', 'INTERNATIONAL_PRIORITY']:
                #                     ship_request.RequestedShipment.SpecialServicesRequested.SpecialServiceTypes = ['ELECTRONIC_TRADE_DOCUMENTS']
                #                     ship_request.RequestedShipment.SpecialServicesRequested.EtdDetail.RequestedDocumentCopies = ['COMMERCIAL_INVOICE']
                #                     ship_request.RequestedShipment.ShippingDocumentSpecification.ShippingDocumentTypes = ['COMMERCIAL_INVOICE']
                #                     ship_request.RequestedShipment.ShippingDocumentSpecification.CertificateOfOrigin.DocumentFormat.ImageType = "PDF"
                #                     ship_request.RequestedShipment.ShippingDocumentSpecification.CertificateOfOrigin.DocumentFormat.StockType = ['PAPER_LETTER']
                # This indicates if the top or bottom of the label comes out of the printer first.
                # BOTTOM_EDGE_OF_TEXT_FIRST, TOP_EDGE_OF_TEXT_FIRST
                ship_request.RequestedShipment.LabelSpecification.LabelPrintingOrientation = 'BOTTOM_EDGE_OF_TEXT_FIRST'

                # Specify the order in which the labels will be returned : SHIPPING_LABEL_FIRST, SHIPPING_LABEL_LAST
                ship_request.RequestedShipment.LabelSpecification.LabelOrder = "SHIPPING_LABEL_FIRST"

                for sequence, package in enumerate(picking.package_ids, start=1):
                    # A multiple-package shipment (MPS) consists of two or more packages shipped to the same recipient.
                    # The first package in the shipment request is considered the master package.

                    # Note: The maximum number of packages in an MPS request is 200.
                    package_weight = self.company_id.weight_convertion(self.fedex_weight_uom, package.shipping_weight)
                    ship_request = self.add_fedex_package(ship_request, package_weight, package_count, number=sequence,
                                                          master_tracking_id=fedex_master_tracking_id,package_id=package)
                    # ship_request = self.add_fedex_package(picking,ship_request, package_weight, package_count, number=sequence, master_tracking_id=fedex_master_tracking_id,package=package)
                    if self.fedex_onerate:
                        ship_request.RequestedShipment.SpecialServicesRequested.SpecialServiceTypes = ['FEDEX_ONE_RATE']
                    if self.is_cod and picking.sale_id and picking.sale_id.fedex_third_party_account_number_sale_order == False:
                        #ship_request.RequestedShipment.SpecialServicesRequested.SpecialServiceTypes = ['COD']
                        cod_vals = {'Amount': picking.sale_id.amount_total + picking.carrier_price,
                                    'Currency': picking.sale_id.company_id.currency_id.name}
                        ship_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodCollectionAmount = cod_vals
                        ship_request.RequestedShipment.SpecialServicesRequested.CodDetail.CollectionType.value = "%s" % (
                            self.fedex_collection_type)

                        ship_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Contact.PersonName = shipper_address.name if not shipper_address.is_company else ''
                        ship_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Contact.CompanyName = shipper_address.name if shipper_address.is_company else ''
                        ship_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Contact.PhoneNumber = shipper_address.phone
                        ship_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Address.StreetLines = shipper_address.street and shipper_address.street2 and [
                            shipper_address.street, shipper_address.street2] or [shipper_address.street]
                        ship_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Address.City = shipper_address.city or None
                        ship_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Address.StateOrProvinceCode = shipper_address.state_id and shipper_address.state_id.code or None
                        ship_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Address.PostalCode = shipper_address.zip
                        ship_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Address.CountryCode = shipper_address.country_id.code

                    ship_request.send_request()
                    shipping_charge, tracking_number, label_binary_data, cod_details, cod_error_message = self.get_fedex_tracking_and_label(
                        ship_request,self.is_cod and picking.sale_id and picking.sale_id.fedex_third_party_account_number_sale_order == False)
                    picking.message_post(body=cod_error_message if cod_error_message else "")
                    if cod_details:
                        attachments.append(
                            ('Fedex_COD_RETURN%s.%s' % (tracking_number, self.fedex_shipping_label_file_type),
                             cod_details))
                    attachments.append(
                        ('Fedex-%s.%s' % (tracking_number, self.fedex_shipping_label_file_type), label_binary_data))
                    exact_price += float(shipping_charge)
                    traking_number.append(tracking_number)
                    package.custom_tracking_number = tracking_number
                    if sequence == 1 and package_count > 1:
                        fedex_master_tracking_id = ship_request.response.CompletedShipmentDetail.MasterTrackingId.TrackingNumber
                if total_bulk_weight:
                    order = picking.sale_id
                    if self.fedex_service_type in ['INTERNATIONAL_ECONOMY', 'INTERNATIONAL_FIRST',
                                                   'INTERNATIONAL_PRIORITY'] or (
                            picking.partner_id.country_id.code == 'IN' and picking.picking_type_id.warehouse_id.partner_id.country_id.code == 'IN'):
                        company = order.company_id or picking.company_id or self.env.user.company_id
                        order_currency = picking.sale_id.currency_id or picking.company_id.currency_id
                        commodity_country_of_manufacture = picking.picking_type_id.warehouse_id.partner_id.country_id.code
                        commodity_weight_units = self.fedex_weight_uom
                        total_commodities_amount = 0.0
                        for operation in picking.move_line_ids:
                            commodity_amount = order_currency._convert(operation.product_id.list_price, order_currency,
                                                                       company, order.date_order or fields.Date.today())
                            total_commodities_amount += (commodity_amount * operation.qty_done)
                            Commodity = ship_request.create_wsdl_object_of_type('Commodity')
                            Commodity.UnitPrice.Currency = order_currency.name
                            Commodity.UnitPrice.Amount = commodity_amount
                            Commodity.NumberOfPieces = '1'
                            Commodity.CountryOfManufacture = commodity_country_of_manufacture
                            Commodity.Weight.Units = commodity_weight_units
                            Commodity.Weight.Value = self.company_id.weight_convertion(self.fedex_weight_uom,
                                                                                       operation.product_id.weight * operation.qty_done)
                            Commodity.Description = operation.product_id.name
                            Commodity.Quantity = operation.qty_done
                            Commodity.QuantityUnits = 'EA'
                            ship_request.RequestedShipment.CustomsClearanceDetail.Commodities.append(Commodity)
                        ship_request.RequestedShipment.CustomsClearanceDetail.DutiesPayment.PaymentType = "RECIPIENT" if order.fedex_bill_by_third_party_sale_order else "SENDER"
                        ship_request.RequestedShipment.CustomsClearanceDetail.DutiesPayment.Payor.ResponsibleParty.AccountNumber = order.fedex_third_party_account_number_sale_order if order.fedex_bill_by_third_party_sale_order else self.company_id and self.company_id.fedex_account_number
                        ship_request.RequestedShipment.CustomsClearanceDetail.DutiesPayment.Payor.ResponsibleParty.Address.CountryCode = picking.picking_type_id.warehouse_id.partner_id.country_id.code
                        ship_request.RequestedShipment.CustomsClearanceDetail.CustomsValue.Amount = total_commodities_amount
                        ship_request.RequestedShipment.CustomsClearanceDetail.CustomsValue.Currency = picking.sale_id.currency_id.name or picking.company_id.currency_id.name

                    ship_request = self.add_fedex_package(ship_request, total_bulk_weight, 1,
                                                          number=1,
                                                          master_tracking_id=fedex_master_tracking_id,package_id=False)
                    if self.fedex_onerate:
                        ship_request.RequestedShipment.SpecialServicesRequested.SpecialServiceTypes = ['FEDEX_ONE_RATE']
                    if self.is_cod and order.fedex_bill_by_third_party_sale_order == False:
                        #ship_request.RequestedShipment.SpecialServicesRequested.SpecialServiceTypes = ['COD']
                        cod_vals = {'Amount': picking.sale_id.amount_total + picking.carrier_price,
                                    'Currency': picking.sale_id.company_id.currency_id.name}
                        ship_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodCollectionAmount = cod_vals
                        ship_request.RequestedShipment.SpecialServicesRequested.CodDetail.CollectionType.value = "%s" % (
                            self.fedex_collection_type)

                        ship_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Contact.PersonName = shipper_address.name if not shipper_address.is_company else ''
                        ship_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Contact.CompanyName = shipper_address.name if shipper_address.is_company else ''
                        ship_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Contact.PhoneNumber = shipper_address.phone
                        ship_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Address.StreetLines = shipper_address.street and shipper_address.street2 and [
                            shipper_address.street, shipper_address.street2] or [shipper_address.street]
                        ship_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Address.City = shipper_address.city or None
                        ship_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Address.StateOrProvinceCode = shipper_address.state_id and shipper_address.state_id.code or None
                        ship_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Address.PostalCode = shipper_address.zip
                        ship_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodRecipient.Address.CountryCode = shipper_address.country_id.code

                    ship_request.send_request()
                    shipping_charge, tracking_number, label_binary_data, cod_details, cod_error_message = self.get_fedex_tracking_and_label(
                        ship_request,self.is_cod and order.fedex_bill_by_third_party_sale_order == False)
                    picking.message_post(body=cod_error_message if cod_error_message else "")
                    if cod_details:
                        attachments.append(
                            ('Fedex_COD_RETURN%s.%s' % (tracking_number, self.fedex_shipping_label_file_type),
                             cod_details))

                    exact_price += float(shipping_charge)
                    traking_number.append(tracking_number)
                    attachments.append(
                        ('Fedex-%s.%s' % (tracking_number, self.fedex_shipping_label_file_type), label_binary_data))
                msg = (_('<b>Shipment created!</b><br/>'))
                picking.message_post(body=msg, attachments=attachments)
            except FedexError as ERROR:
                raise ValidationError(ERROR.value)
            except FedexFailure as ERROR:
                raise ValidationError(ERROR.value)
            except Exception as e:
                raise ValidationError(e)
            res = res + [{'exact_price': exact_price + self.add_custom_margin,
                          'tracking_number': fedex_master_tracking_id if fedex_master_tracking_id else ",".join(
                              traking_number)}]
        return res

    def fedex_shipping_provider_get_tracking_link(self, pickings):
        res = ""
        for picking in pickings:
            link = "https://www.fedex.com/apps/fedextrack/?action=track&trackingnumber="
            res = '%s %s' % (link, picking.carrier_tracking_ref)
        return res

    def fedex_shipping_provider_cancel_shipment(self, picking):
        try:
            FedexConfig = self.company_id.get_fedex_api_object(self.prod_environment)
            delete_request = FedexDeleteShipmentRequest(FedexConfig)
            delete_request.DeletionControlType = "DELETE_ALL_PACKAGES"
            delete_request.TrackingId.TrackingNumber = picking.carrier_tracking_ref.split(',')[
                0]  # master tracking number
            delete_request.TrackingId.TrackingIdType = 'FEDEX'
            delete_request.send_request()
            assert delete_request.response.HighestSeverity in ['SUCCESS', 'WARNING'], \
                "%s : %s" % (
                    picking.carrier_tracking_ref.split(',')[0], delete_request.response.Notifications[0].Message)
        except FedexError as ERROR:
            raise ValidationError(ERROR.value)
        except FedexFailure as ERROR:
            raise ValidationError(ERROR.value)
        except Exception as e:
            raise ValidationError(e)
