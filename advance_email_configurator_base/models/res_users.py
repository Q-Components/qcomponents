from odoo import _, api, fields, models
import logging

_logger = logging.getLogger(__name__)
import smtplib


class ResUser(models.Model):
    _inherit = ['res.users']

    smtp_authentication = fields.Selection([('login', 'Username')],default='login')
