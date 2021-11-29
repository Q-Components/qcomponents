from odoo import models, fields,api
from odoo.addons.ups_shipping_odoo_integration.ups_api.ups_request import UPS_API


class ResCompany(models.Model):
    _inherit = "res.company"
    use_ups_shipping_provider = fields.Boolean(copy=False, string="Are You Use UPS Shipping Provider.?", help="If use UPS shipping provider than value set TRUE.",default=False)

    access_license_number = fields.Char("AccessLicenseNumber")
    ups_userid = fields.Char("UPS UserId")
    ups_password = fields.Char("UPS Password")
    ups_shipper_number = fields.Char("UPS Shipper Number")
    check_recipient_address = fields.Boolean(copy=False, string="Check Recipient Address")
    mail_template_id = fields.Many2one('mail.template', 'E-mail Template')
    is_automatic_shipment_mail = fields.Boolean('Automatic Send Shipment Confirmation Mail')


    def get_ups_api_object(self, environment, service_name, ups_user_id, ups_password, ups_access_license_number):
        api = UPS_API(environment, service_name, ups_user_id, ups_password, ups_access_license_number, timeout=500)
        return api


    def weight_convertion(self, weight_unit, weight):
        uom_id = self.env['product.template']._get_weight_uom_id_from_ir_config_parameter()
        pound_for_kg = 2.20462
        ounce_for_lb = 16
        ounce_for_kg = 35.274
        if uom_id.name in ['lb','lbs','LB','LBS'] and weight_unit in ["LB", "LBS"]:
            return round(weight, 3)
        elif uom_id.name in ['kg','KG'] and weight_unit in ["LB", "LBS"]:
            return round(weight * pound_for_kg, 3)
        elif uom_id.name in ['lb','lbs','LB','LBS'] and weight_unit in ["OZ", "OZS"]:
            return round(weight * ounce_for_lb, 3)
        elif uom_id.name in ['kg','KG'] and weight_unit in ["OZ", "OZS"]:
            return round(weight * ounce_for_kg, 3)
        else:
            return round(weight, 3)

