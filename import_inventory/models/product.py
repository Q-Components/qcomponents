# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import Warning
from odoo import models, fields, exceptions, api, _


class ProductTemplateInherit(models.Model):
    _inherit = "product.template"

    x_studio_alternate_number = fields.Char(string='Alternate Number')
    x_studio_category = fields.Char(string='Internal Category')
    x_studio_rohs = fields.Char(string='RoHs')
    x_studio_file_attachment = fields.Binary('Data Sheet')
    x_studio_file_attachment_filename = fields.Char('Attachment Name')
    x_studio_field_sUWfQ = fields.Char(string='ItemNo')
    x_studio_manufacturer = fields.Char(string='Manufacturer')
    x_studio_date_code_1 = fields.Char(string='Date Code')
    x_studio_condition_1 = fields.Char(string='Condition')
    x_studio_package = fields.Char(string='Mfg Packaging')
    x_studio_origin_code = fields.Char(string='Origin Code')
    x_studio_country_of_origin = fields.Char(string='Country of Origin')