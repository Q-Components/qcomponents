# -*- coding: utf-8 -*-
#################################################################################
##    Copyright (c) 2018-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#    You should have received a copy of the License along with this program.
#    If not, see <https://store.webkul.com/license.html/>
#################################################################################

from odoo import api, fields, models,_
import logging
_logger = logging.getLogger(__name__)

SignatureOptionHelp=_("""Use FedEx Delivery Signature Options to specify the level of signature required for FedEx Express and Freight shipments.\n
To have FedEx obtain a signature when your package is delivered, choose from one of four FedEx signature options:\n

#Deliver Without Signature\n
No signature is required for delivery. Select this option by coding the field as 2399,"1" to deliver the shipment without collecting a signature. This is the default for all residential deliveries. This signature level is not available to commercial addresses. No surcharge is applied.\n
#Indirect Signature Required\n
A signature can be obtained from any individual at the address specified on the package, from a signed door tag, or from an individual at a neighboring address. Select this option by coding the field as 2399,"2" to deliver the shipment when an indirect signature is obtained. FedEx charges a fee for this service when shipments are delivered to residential addresses. This service option is available for FedEx Express. Address corrections are permitted.\n
#Direct Signature Required\n
A signature can be obtained from any individual at the address specified on the package. Select this option by coding the field as 2399,"3" to deliver the shipment with when a direct signature is obtained. FedEx charges a fee for this service. This service option is available for FedEx Express. Address corrections are permitted.\n
#Adult Signature Required\n
A signature can only be obtained from an individual 21 years of age or older at the address specified on the package. Select this option by coding the field as 2399,"4" to deliver the shipment only when an adult signature is obtained. A government-issued, photo ID is required for age verification. This service option incurs a fee for all deliveries. This service option is available for FedEx Express. Address corrections are not permitted.

    """)

PriorityAlertHelp=_("""The FedEx Priority Alert and Priority Alert Plus services are supported as an option for the following shipment services:\n
·       FedEx First Overnight®\n
·       FedEx First Overnight® Freight (for contracted accounts only)\n
·       FedEx Priority Overnight®\n
·       FedEx 1Day® Freight (Express)\n
·       FedEx International Priority®\n
·       FedEx International First®\n
·       FedEx Europe First®\n
·       FedEx International Priority® Freight\n
·       FedEx International Priority DirectDistribution® (IPD), includes Single Point of Clearance (SPOC)\n
""")
EdtRequestTypeHelp = _("""
""")
HelpDropoff = _(
    "FedEx has several drop-off types, listed below:Regular Pickup - The shipper already has an every-day pickup scheduled with a courier.Request Courier - The shipper will call FedEx to ask for a courier.Drop Box - The shipper will drop the package in a FedEx drop box.Business Service Center - The shipper will drop off the package at an authorized FedEx business service center.Station - The shipper will drop off the package at a FedEx Station. "
)

ServiceType = [
    ('STANDARD_OVERNIGHT', 'Standard Overnight'),
    ('PRIORITY_OVERNIGHT', 'Priority Overnight'),
    ('FEDEX_GROUND', 'Fedex Ground'),
    ('FEDEX_EXPRESS_SAVER', 'Fedex Express Saver'),
    ('EUROPE_FIRST_INTERNATIONAL_PRIORITY',
     'Europe First International Priority'),
    ('FEDEX_1_DAY_FREIGHT', 'Fedex 1 Day Freight'),
    ('FEDEX_2_DAY', 'Fedex 2 Day'),
    ('FEDEX_2_DAY_AM', 'Fedex 2 Day AM'),
    ('FEDEX_2_DAY_FREIGHT', 'Fedex 2 Day Freight'),
    ('FEDEX_3_DAY_FREIGHT', 'Fedex 3 Day Freight'),
    ('FEDEX_FIRST_FREIGHT', 'Fedex First Freight'),
    ('FEDEX_FREIGHT_PRIORITY', 'FedEx Freight Priority'),
    ('FIRST_OVERNIGHT', 'First Overnight'),
    ('GROUND_HOME_DELIVERY', 'Ground Home Delivery'),
    ('INTERNATIONAL_ECONOMY', 'International Economy'),
    ('INTERNATIONAL_ECONOMY_FREIGHT', 'International Economy Freight'),
    ('INTERNATIONAL_FIRST', 'International First'),
    ('INTERNATIONAL_PRIORITY', 'International Priority'),
    ('INTERNATIONAL_PRIORITY_FREIGHT', 'International Priority Freight'),
    ('SMART_POST', 'Smart Post')
]
DropoffType = [
    ('REGULAR_PICKUP', 'Regular Pickup'),
    ('REQUEST_COURIER', 'Request Courier'),
    ('DROP_BOX', 'Drop Box'),
    ('BUSINESS_SERVICE_CENTER', 'Business Service Center'),
    ('STATION', 'Station')
]
PackagingType = [
    ('YOUR_PACKAGING', 'Your Packaging'),
    ('FEDEX_PAK', 'FedEx Pak'),
    ('FEDEX_BOX', 'FedEx Box'),
    ('FEDEX_TUBE', 'FedEx Tube'),
    ('FEDEX_10KG_BOX', 'FEDEX_10KG_BOX'),
     ('FEDEX_25KG_BOX', 'FEDEX_25KG_BOX'),
     ('FEDEX_ENVELOPE', 'FEDEX_ENVELOPE'),

]
PaymentType = [
    ('SENDER', 'Sender'),
    ('RECIPIENT', 'Recipient'),
    ('THIRD_PARTY', 'Third Party'),
    ('ACCOUNT', 'Account'),
    ('COLLECT', 'Collect'),
]
LabelStockType = [
    ('PAPER_4X6', 'PAPER_4X6'),
    ('PAPER_4X8', 'PAPER_4X8'),
    ('PAPER_4X9', 'PAPER_4X9'),
    ('PAPER_7X4.75', 'PAPER_7X4.75'),
    ('PAPER_8.5X11_BOTTOM_HALF_LABEL', 'PAPER_8.5X11_BOTTOM_HALF_LABEL'),
    ('PAPER_8.5X11_TOP_HALF_LABEL', 'PAPER_8.5X11_TOP_HALF_LABEL'),
    ('PAPER_LETTER', 'PAPER_LETTER')
]
TrackingIdType = [
    ('FEDEX', 'FEDEX'),
    ('EXPRESS', 'EXPRESS'),
    ('GROUND', 'GROUND'),
    ('USPS', 'USPS'),
]


SignatureOption = [
    ('DIRECT','DIRECT'),
    ('INDIRECT','INDIRECT'),
    ('ADULT','ADULT'),
    ('NO_SIGNATURE_REQUIRED','NO_SIGNATURE_REQUIRED')
]
EdtRequestType = [
    ('NONE','NONE'),
    ('ALL','ALL'),
]
Boolean = [
    ('yes', 'Yes'),
    ('no', 'NO'),
]

CollectionType = [
    ('ANY', 'Any Payment Type'),
    ('CASH', 'Currency'),
    ('COMPANY_CHECK', 'Company Cheque'),
    ('GUARANTEED_FUNDS', 'Guaranteed funds'),
    ('PERSONAL_CHECK', 'Personal Cheque')
]

TinType = [
    ('BUSINESS_NATIONAL', 'Business National'),
    ('BUSINESS_STATE', 'Business State'),
    ('BUSINESS_UNION', 'Business Union'),
    ('PERSONAL_NATIONAL', 'Personal National'),
    ('PERSONAL_STATE', 'PERSONAL State')
]
# class ChooseDeliveryPackage(models.TransientModel):
#     _inherit = "choose.delivery.package"
#     fedex_signature_option = fields.Selection(
#         string='FedEx Signature Option',
#         selection=SignatureOption,
#         default='NO_SIGNATURE_REQUIRED',
#         help=SignatureOptionHelp
#     )
#     fedex_priority_alert = fields.Selection(
#         selection=Boolean,
#         string='Priority Alert',
#         default='no',
#         help=PriorityAlertHelp
#     )
#     fedex_priority_content = fields.Text(
#         string='Details'
#     )
#     fedex_edt_request_type = fields.Selection(
#         selection=EdtRequestType,
#         string='EdtRequestType',
#         default='NONE',
#         help=EdtRequestTypeHelp
#     )
#     def get_shipping_fields(self):
#         fedex_fields = ['fedex_signature_option','fedex_priority_alert','fedex_priority_content','fedex_edt_request_type']
#         return super(ChooseDeliveryPackage,self).get_shipping_fields()+fedex_fields



class ProductPackage(models.Model):
    _inherit = 'product.package'
    delivery_type = fields.Selection(
        selection_add=[('fedex', 'FedEx')]
    )

class ProductPackaging(models.Model):
    _inherit = 'product.packaging'
    package_carrier_type = fields.Selection(
        selection_add=[('fedex', 'FedEx')]
    )
    fedex_signature_option = fields.Selection(
        string='FedEx Signature Option',
        selection=SignatureOption,
        default='NO_SIGNATURE_REQUIRED',
        help=SignatureOptionHelp
    )
    fedex_priority_alert = fields.Selection(
        selection=Boolean,
        string='Priority Alert',
        default='no',
        help=PriorityAlertHelp
    )
    fedex_priority_content = fields.Text(
        string='Details'
    )
    fedex_edt_request_type = fields.Selection(
        selection=EdtRequestType,
        string='EdtRequestType',
        default='NONE',
        help=EdtRequestTypeHelp
    )
class ShippingFedex(models.Model):
    _inherit = "delivery.carrier"
    delivery_type = fields.Selection(
        selection_add=[('fedex', 'FedEx')]
    )
    fedex_dropofftype = fields.Many2one(
        comodel_name='delivery.carrier.fedex.dropofftype',
        string='Drop-off Type',
        help=HelpDropoff
    )
    fedex_paymentyype = fields.Selection(
        selection=PaymentType,
        string='Payment Type',
        help="Who pays for the rate_request? ",
        default="RECIPIENT",
    )
    fedex_servicetype = fields.Many2one(
        comodel_name='delivery.carrier.fedex.service',
        string='Service Type'
    )
    fedex_reciver_account_number = fields.Char(
        string='Recipient Account NO.'
    )
    fedex_label_stock_type = fields.Selection(
        selection=LabelStockType,
        string='Label Stock Type',
        default='PAPER_LETTER'
    )
    fedex_trackingid_type = fields.Selection(
        selection=TrackingIdType,
        string='Tracking ID Type ',
        default='FEDEX'
    )
    fedex_key=fields.Char(
        string='key',
    )
    fedex_password=fields.Char(
        string='Password',
    )

    fedex_account_no=fields.Char(
        string='Account No.',
    )
    fedex_meter_no=fields.Char(
        string='Meter No.',
    )
    fedex_integration_id=fields.Char(
        string='Integration ID',
    )
    
    @api.model
    def _get_config(self,key):
        if key=='fedex.config.settings':
            data  = self.read(['fedex_key','fedex_password','fedex_account_no','fedex_meter_no','fedex_integration_id','prod_environment'])[0]
            data['fedex_enviroment'] ='production' if data['prod_environment'] else  'test'  

            return data
        return super(ShippingFedex,self)._get_config(key)
    


class ShippingFedexDropofftype(models.Model):
    _name = "delivery.carrier.fedex.dropofftype"

    name = fields.Char(
        string='Name',
        required=1
    )
    code = fields.Char(
        string='Code',
        required=1
    )

class ShippingFedexServiceType(models.Model):
    _name = "delivery.carrier.fedex.service"

    name = fields.Char(
        string='Name',
        required=1
    )
    code = fields.Char(
        string='Code',
        required=1
    )

class CODShippingServices(models.Model):
    _inherit = 'stock.picking'
    is_cod = fields.Boolean(string="C.O.D")
    collection_type = fields.Selection(selection=CollectionType, string="Collection Type", default="ANY")

    @api.onchange('is_cod')
    def check_payment_type(self):
        for obj in self:
            if obj.is_cod:
                obj.carrier_id.fedex_paymentyype = 'SENDER'



class BillingDetailsPartner(models.Model):
    _inherit = 'res.partner'
    
    tin_type = fields.Selection(selection=TinType, string="Tin Type", default='BUSINESS_NATIONAL')
