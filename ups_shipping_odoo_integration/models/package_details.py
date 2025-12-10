from odoo import models, fields

class PackageDetails(models.Model):
    _inherit = 'stock.package.type'
    package_carrier_type = fields.Selection(selection_add=[("ups_provider", "UPS")],
                                            ondelete={'ups_provider': 'set default'})