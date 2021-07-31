from odoo.exceptions import Warning,ValidationError
from odoo import models, fields, api, _
from odoo.addons.fedex_shipping_odoo_integration.fedex.base_service import FedexError, FedexFailure
from odoo.addons.fedex_shipping_odoo_integration.fedex.tools.conversion import basic_sobject_to_dict
from odoo.addons.fedex_shipping_odoo_integration.fedex.services.rate_service import FedexRateServiceRequest
from odoo.addons.fedex_shipping_odoo_integration.fedex.services.ship_service import FedexDeleteShipmentRequest
from odoo.addons.fedex_shipping_odoo_integration.fedex.services.ship_service import FedexProcessShipmentRequest
from odoo.addons.fedex_shipping_odoo_integration.fedex.services.address_validation_service import FedexAddressValidationRequest

class FedExPackageDetails(models.Model):
    _inherit = "stock.picking"

    def create_return_order(self):
        for picking in self:
            with_context = self._context.copy()
            with_context.update({'use_fedex_return': True})
            res = self.carrier_id.with_context(with_context).fedex_shipping_provider_send_shipping(picking)
            picking.write({'carrier_tracking_ref': res[0].get('tracking_number', ''),
                           'carrier_price': res[0].get('exact_price', 0.0)})

    # @api.multi
    # def button_validate(self):
    #     self.ensure_one()
    #     for move_id in self.move_ids_without_package:
    #         if move_id.picking_id.picking_type_code == 'outgoing':
    #             move_id.quantity_done=move_id.reserved_availability
    #     return super(FedExPackageDetails, self).button_validate()


    def manage_fedex_packages(self, rate_request, package_data, number=1,total_weight=0.0):
        package_weight = rate_request.create_wsdl_object_of_type('Weight')
        package_weight.Value = total_weight
        package_weight.Units = self.carrier_id.fedex_weight_uom
        package = rate_request.create_wsdl_object_of_type('RequestedPackageLineItem')
        package.Weight = package_weight
        package_data = package_data.packaging_id
        if self.carrier_id.fedex_default_product_packaging_id.shipper_package_code == 'YOUR_PACKAGING':
            package.Dimensions.Length = package_data and package_data.length
            package.Dimensions.Width = package_data and package_data.width
            package.Dimensions.Height =  package_data and package_data.height
            package.Dimensions.Units = 'IN' if self.carrier_id.fedex_weight_uom == 'LB' else 'CM'
        package.PhysicalPackaging = 'BOX'
        package.GroupPackageCount = 1
        if number:
            package.SequenceNumber = number
        return package

    def fedex_shipping_provider_get_shipping_charges(self):
        return self.get_fedex_rate()


    def get_fedex_rate(self):
        self.ensure_one()
        total_weight=0.0
        if self.carrier_id.delivery_type=='fedex_shipping_provider':
            shipping_charge = 0.0

            # Shipper and Recipient Address
            shipper_address = self.picking_type_id.warehouse_id.partner_id
            recipient_address = self.partner_id
            shipping_credential = self.carrier_id.company_id

            # check sender Address
            if not shipper_address.zip or not shipper_address.city or not shipper_address.country_id:
                raise Warning(_("Please Define Proper Sender Address!"))

            # check Receiver Address
            if not recipient_address.zip or not recipient_address.city or not recipient_address.country_id:
                raise Warning(_("Please Define Proper Recipient Address!"))
            try:
                # This is the object that will be handling our request.
                FedexConfig = shipping_credential.get_fedex_api_object(self.carrier_id.prod_environment)
                rate_request = FedexRateServiceRequest(FedexConfig)
                package_type = self.carrier_id.fedex_default_product_packaging_id.shipper_package_code
                rate_request = self.carrier_id.prepare_shipment_request(shipping_credential, rate_request, shipper_address,
                                                             recipient_address, package_type,self.sale_id)
                rate_request.RequestedShipment.PreferredCurrency = self.company_id and self.company_id.currency_id and self.company_id.currency_id.name

                if not self.package_ids:
                    total_weight=self.company_id.weight_convertion(self.carrier_id and self.carrier_id.fedex_weight_uom,self.weight)
                    package = self.carrier_id.manage_fedex_packages(rate_request, total_weight)
                    rate_request.add_package(package)

                for sequence, package in enumerate(self.package_ids, start=1):
                    total_weight = self.company_id.weight_convertion(
                        self.carrier_id and self.carrier_id.fedex_weight_uom, package.shipping_weight)
                    package = self.manage_fedex_packages(rate_request, package, sequence,total_weight)
                    rate_request.add_package(package)

                if self.carrier_id.fedex_onerate:
                    rate_request.RequestedShipment.SpecialServicesRequested.SpecialServiceTypes = ['FEDEX_ONE_RATE']
                if self.carrier_id.is_cod and self.sale_id and self.sale_id.fedex_third_party_account_number_sale_order == False:
                    rate_request.RequestedShipment.SpecialServicesRequested.SpecialServiceTypes = ['COD']
                    cod_vals = {'Amount': self.sale_id.amount_total + self.carrier_price,
                                'Currency': self.sale_id.company_id.currency_id.name}
                    rate_request.RequestedShipment.SpecialServicesRequested.CodDetail.CodCollectionAmount = cod_vals
                    rate_request.RequestedShipment.SpecialServicesRequested.CodDetail.CollectionType.value = "%s" % (
                        self.carrier_id.fedex_collection_type)

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
                raise Warning(_("Request Data Is Not Correct! %s "%(ERROR.value)))
                # raise ValidationError(ERROR.value)
            except FedexFailure as ERROR:
                raise Warning(_("Request Data Is Not Correct! %s " % (ERROR.value)))
                # raise ValidationError(ERROR.value)
            except Exception as e:
                raise Warning(_("Request Data Is Not Correct! %s " % (e)))
                # raise ValidationError(e)
            for shipping_service in rate_request.response.RateReplyDetails:
                for rate_info in shipping_service.RatedShipmentDetails:
                    shipping_charge = float(rate_info.ShipmentRateDetail.TotalNetFedExCharge.Amount)
                    shipping_charge_currency = rate_info.ShipmentRateDetail.TotalNetFedExCharge.Currency
                    if self.company_id and self.company_id.currency_id and self.company_id.currency_id.name != rate_info.ShipmentRateDetail.TotalNetFedExCharge.Currency:
                        rate_currency = self.env['res.currency'].search([('name', '=', shipping_charge_currency)],
                                                                        limit=1)
                        if rate_currency:
                            shipping_charge = rate_currency.compute(float(shipping_charge), self.company_id and self.company_id.currency_id and self.company_id.currency_id)
            self.carrier_price=float(shipping_charge) + self.carrier_id.add_custom_margin
        return {
            'effect': {
                'fadeout': 'slow',
                'message': "Yeah! Shipping Charge has been retrieved.",
                'img_url': '/web/static/src/img/smile.svg',
                'type': 'rainbow_man',
            }
        }


class FedExPackageDetails(models.Model):
    _inherit = "stock.quant.package"
    custom_tracking_number = fields.Char(string = "FedEx Tracking Number", help = "If tracking number available print it in this field.")
