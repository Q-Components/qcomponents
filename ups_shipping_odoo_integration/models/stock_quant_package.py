from odoo import models, fields


class FedExPackageDetails(models.Model):
    _inherit = "stock.quant.package"

    # For Insurance functionality
    insured_request = fields.Boolean(string="Insured Request",
                                     help="Use this Insured Request required",
                                     default=False)
    insured_amount = fields.Float(string="Insured Amount",
                                  help="Insured Amount or Declare Amount",
                                  default=False)
    ups_cod_parcel_package = fields.Boolean(string='UPS COD Package ?')
    ups_cod_amount_package = fields.Float(string='UPS Parcel COD Amount')
    ups_cod_fund_code_package = fields.Selection(
        [('0', '0 - Check, Cash Cashier Check Money Order'), ('8', '8 - Cashier Check Money Order'), ('1', '1 - Cash'),
         ('9', '9 - Check Cashiers Check Money Order/Personal Check')],
        help="Shipment Level = 1 or 9: "
             "Package Level : 0 or 8 or 9", string="UPS COD Fund Code", default="0")

