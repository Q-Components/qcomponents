from odoo import models, fields, api
from odoo.addons.fedex_shipping_odoo_integration.fedex.config import FedexConfig


class ResCompany(models.Model):
    _inherit = "res.company"
    use_fedex_shipping_provider = fields.Boolean(copy=False, string="Are You Use FedEx Shipping Provider.?",
                                                 help="If use fedEx shipping provider than value set TRUE.",
                                                 default=False)
    use_address_validation_service = fields.Boolean(copy=False, string="Use Address Validation Service",
                                                    help="Use Address Validation service to identify residential area or not.\nTo use address validation services, client need to request fedex to enable this service for his account.By default, The service is disable and you will receive authentication failed.")
    fedex_key = fields.Char(string="Developer Key", help="Developer key", copy=False)
    fedex_password = fields.Char(copy=False, string='Password',
                                 help="The Fedex-generated password for your Web Systems account. This is generally emailed to you after registration.")
    fedex_account_number = fields.Char(copy=False, string='Account Number',
                                       help="The account number sent to you by Fedex after registering for Web Services.")
    fedex_meter_number = fields.Char(copy=False, string='Meter Number',
                                     help="The meter number sent to you by Fedex after registering for Web Services.")
    fedex_integration_id = fields.Char(copy=False, string='Integration ID',
                                       help="The integrator string sent to you by Fedex after registering for Web Services.")

    def get_fedex_api_object(self, prod_environment=False):
        return FedexConfig(key=self.fedex_key,
                           password=self.fedex_password,
                           account_number=self.fedex_account_number,
                           meter_number=self.fedex_meter_number,
                           integrator_id=self.fedex_integration_id,
                           use_test_server=not prod_environment)

    def weight_convertion(self, weight_unit, weight):
        pound_for_kg = 2.20462
        ounce_for_kg = 35.274
        ounce_for_lb = 16
        uom_id = self.env['product.template']._get_weight_uom_id_from_ir_config_parameter()
        if weight_unit in ["LB", "LBS", "lb", "lbs"] and uom_id.name in ['lb', 'lbs']:
            return round(weight, 3)
        elif weight_unit in ["LB", "LBS", "lb", "lbs"] and uom_id.name in ['kg']:
            return round(weight * pound_for_kg, 3)
        elif weight_unit in ["OZ", "OZS"] and uom_id.name in ['kg']:
            return round(weight * ounce_for_kg, 3)
        elif weight_unit in ["OZ", "OZS"] and uom_id.name in ['lb', 'lbs']:
            return round(weight * ounce_for_lb, 3)
        else:
            return round(weight, 3)
