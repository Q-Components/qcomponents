from odoo import models, fields


class AccountMove(models.Model):
    _inherit = "account.move"

    instance_id = fields.Many2one("shopify.instance.integration", "Shopify Instance")