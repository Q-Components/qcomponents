from odoo.exceptions import Warning,ValidationError, UserError
from odoo import models, fields, api, _
from odoo.addons.fedex_shipping_odoo_integration.fedex.base_service import FedexError, FedexFailure
from odoo.addons.fedex_shipping_odoo_integration.fedex.tools.conversion import basic_sobject_to_dict
from odoo.addons.fedex_shipping_odoo_integration.fedex.services.rate_service import FedexRateServiceRequest
from odoo.addons.fedex_shipping_odoo_integration.fedex.services.ship_service import FedexDeleteShipmentRequest
from odoo.addons.fedex_shipping_odoo_integration.fedex.services.ship_service import FedexProcessShipmentRequest
from odoo.addons.fedex_shipping_odoo_integration.fedex.services.address_validation_service import FedexAddressValidationRequest
import logging

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = "sale.order"

    fedex_third_party_account_number_sale_order = fields.Char(copy=False, string='FexEx Third-Party Account Number',
                                                              help="Please Enter the Third Party account number ")
    fedex_bill_by_third_party_sale_order = fields.Boolean(string="FedEx Third Party Payment", copy=False, default=False,
                                                          help="when this fields is true,then we can visible fedex_third party account number")

    @api.depends('order_line')
    def _compute_bulk_weight(self):
        weight = 0.0
        for line in self.order_line:
                weight += line.product_uom_id._compute_quantity(line.product_uom_qty, line.product_id.uom_id) * line.product_id.weight
        self.weight_bulk = weight
    
    
    def manage_fedex_packages(self, rate_request, package_data, number=1,total_weight=0.0):
        package_weight = rate_request.create_wsdl_object_of_type('Weight')
        package_weight.Value = total_weight
        package_weight.Units = self.carrier_id.fedex_weight_uom
        package = rate_request.create_wsdl_object_of_type('RequestedPackageLineItem')
        package.Weight = package_weight
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
        res=self.get_fedex_rate()
        self.set_delivery_line()
        return res


    def get_fedex_rate(self):
        self.ensure_one()
        immediate_payment_term_id = self.env.ref('account.account_payment_term_immediate').id
        if self.carrier_id.delivery_type=='fedex_shipping_provider':
            shipping_charge = 0.0
            weight = 0.0
            for line in self.order_line:
                weight += line.product_uom._compute_quantity(line.product_uom_qty, line.product_id.uom_id) * line.product_id.weight
            
            _logger.info('Product Weight : %s ' % (weight))
            # Shipper and Recipient Address
            shipper_address = self.warehouse_id.partner_id
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
                                                             recipient_address, package_type,self)
                rate_request.RequestedShipment.PreferredCurrency = self.company_id and self.company_id.currency_id and self.company_id.currency_id.name
                
                _logger.info('Fedex Package Details : %s ' % (self.custom_package_ids))
                if not self.custom_package_ids:
                    
                    total_weight=self.company_id.weight_convertion(self.carrier_id and self.carrier_id.fedex_weight_uom,weight)
                    package = self.carrier_id.manage_fedex_packages(rate_request, total_weight)
                    rate_request.add_package(package)
                
                    _logger.info('Total Weight : %s ' % (total_weight))
                    _logger.info('Package : %s ' % (package))
                

                for sequence, package in enumerate(self.custom_package_ids, start=1):
                    total_weight = self.company_id.weight_convertion(
                        self.carrier_id and self.carrier_id.fedex_weight_uom, package.shipping_weight)
                    package = self.manage_fedex_packages(rate_request, package, sequence,total_weight)
                    rate_request.add_package(package)

                if self.carrier_id.fedex_onerate:
                    rate_request.RequestedShipment.SpecialServicesRequested.SpecialServiceTypes = ['FEDEX_ONE_RATE']
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
            self.delivery_price=float(shipping_charge) + self.carrier_id.add_custom_margin
            self.delivery_rating_success = True
            if self.payment_term_id and self.payment_term_id.id == immediate_payment_term_id:
                self.set_delivery_line()
        return {
            'effect': {
                'fadeout': 'slow',
                'message': "Yeah! Shipping Charge has been retrieved.",
                'img_url': '/web/static/src/img/smile.svg',
                'type': 'rainbow_man',
            }
        }
    
    def action_confirm(self):
        immediate_payment_term_id = self.env.ref('account.account_payment_term_immediate').id
        if self.payment_term_id and self.payment_term_id.id == immediate_payment_term_id:
            if self.carrier_id and self.carrier_id.delivery_type == 'fedex_shipping_provider' and self.delivery_price <= 0.0 or not self.order_line.filtered(lambda x: not x.is_delivery):
                raise UserError("Before Confirm Sale Order Please Get Delivery Rate and Set Delivery Price in Order Line .Go To Fedex Page --> Click On Get Rate Button")
#             elif self.carrier_id and self.carrier_id.delivery_type == 'fedex' :
#                 self.get_fedex_rate()
#                 self.delivery_rating_sucess = True
#                 self.set_delivery_line()
        return super(SaleOrder, self).action_confirm()
