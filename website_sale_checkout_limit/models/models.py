# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.http import request
from odoo.addons.http_routing.models.ir_http import slug, unslug

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

class Product(models.Model):
    _inherit = ["product.product", 'website.searchable.mixin']
    _name = 'product.product'

    @api.model
    def _search_get_detail(self, website, order, options):
        with_image = options['displayImage']
        with_description = options['displayDescription']
        with_category = options['displayExtraLink']
        with_price = options['displayDetail']
        domains = [website.sale_product_domain()]
        category = options.get('category')
        min_price = options.get('min_price')
        max_price = options.get('max_price')
        # attrib_values = options.get('attrib_values')
        #domains.append([('default_code', '>=', min_price)])

        if category:
            domains.append([('public_categ_ids', 'child_of', unslug(category)[1])])
        if min_price:
            domains.append([('list_price', '>=', min_price)])
        if max_price:
            domains.append([('list_price', '<=', max_price)])
        search_fields = ['x_studio_alternate_number']
        fetch_fields = ['id', 'display_name', 'website_url']
        mapping = {
            'name': {'name': 'display_name', 'type': 'text', 'match': True},
            'website_url': {'name': 'website_url', 'type': 'text', 'truncate': False},
        }
        mapping['image_url'] = {'name': 'image_url', 'type': 'html'}
        mapping['detail'] = {'name': 'price', 'type': 'html', 'display_currency': options['display_currency']}
        mapping['detail_strike'] = {'name': 'list_price', 'type': 'html',
                                    'display_currency': options['display_currency']}

        return {
            'model': 'product.product',
            'base_domain': domains,
            'search_fields': search_fields,
            'fetch_fields': fetch_fields,
            'mapping': mapping,
            'icon': 'fa-shopping-cart',
        }
class ProductTemplate(models.Model):
    _inherit = "product.template"
    _name = 'product.template'

    @api.model
    def _search_get_detail(self, website, order, options):
    	res = super(ProductTemplate, self)._search_get_detail(website, order, options)
    	res['search_fields'].append('x_studio_alternate_number')
    	return res

class Website(models.Model):
    _inherit = 'website'
    _name = "website"

    def _search_get_details(self, search_type, order, options):
        #afsfa
        result = super(Website, self)._search_get_details(search_type, order, options)
        if search_type in ['products', 'products_only', 'all']:
            result.append(self.env['product.product']._search_get_detail(self, order, options))
        return result
