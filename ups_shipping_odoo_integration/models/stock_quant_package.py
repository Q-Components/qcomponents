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

