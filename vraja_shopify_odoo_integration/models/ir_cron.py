from odoo import models, fields


class IrCron(models.Model):
    _inherit = 'ir.cron'

    shopify_instance = fields.Many2one('shopify.instance.integration')
