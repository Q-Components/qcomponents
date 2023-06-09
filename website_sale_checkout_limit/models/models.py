# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.http import request


class Website(models.Model):
    _inherit = "website"

    def check_cart_amount(self):
        order = request.website.sale_get_order()
        ircsudo = self.env['ir.config_parameter'].sudo()
        min_checkout_amount = ircsudo.get_param('website_sale_checkout_limit.min_checkout_amount')
        min_amount_type = ircsudo.get_param('website_sale_checkout_limit.min_amount_type')
        if min_amount_type == 'untaxed':
            untaxed_amount = order.amount_untaxed
            if untaxed_amount < float(min_checkout_amount):
                return False
            else:
                return True

        elif min_amount_type == 'taxed':
            taxed_amount = order.amount_total
            if taxed_amount < float(min_checkout_amount):
                return False
            else:
                return True

    def info_message(self):
        ircsudo = self.env['ir.config_parameter'].sudo()
        info_message = ircsudo.get_param('website_sale_checkout_limit.info_message')
        return info_message


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    min_checkout_amount = fields.Float(string='Minimum Amount to Checkout')
    min_amount_type = fields.Selection([('untaxed', 'Tax Excluded'), ('taxed', 'Tax Included')])
    info_message = fields.Text(string='Message', translate=True)

    def set_values(self):
        res = super(ResConfigSettings, self).set_values()
        self.env['ir.config_parameter'].set_param('website_sale_checkout_limit.min_checkout_amount',
                                                  self.min_checkout_amount)
        self.env['ir.config_parameter'].set_param('website_sale_checkout_limit.min_amount_type',
                                                  self.min_amount_type)
        self.env['ir.config_parameter'].set_param('website_sale_checkout_limit.info_message',
                                                  self.info_message)
        return res

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        ircsudo = self.env['ir.config_parameter'].sudo()
        min_checkout_amount = ircsudo.get_param('website_sale_checkout_limit.min_checkout_amount') or 50
        min_amount_type = ircsudo.get_param('website_sale_checkout_limit.min_amount_type') or 'untaxed'
        info_message = ircsudo.get_param('website_sale_checkout_limit.info_message')

        res.update(
            min_checkout_amount=float(min_checkout_amount),
            min_amount_type=min_amount_type,
            info_message=info_message,
        )
        return res
