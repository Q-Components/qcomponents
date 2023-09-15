# -*- coding: utf-8 -*-

from dataclasses import field
from email.policy import default
from odoo import models, fields, api
from odoo.exceptions import UserError
from algoliasearch.search_client import SearchClient


class AlgoliaSearchApp(models.Model):
    _name = 'algolia.search.app'
    _description = 'Algolia Search App'

    name = fields.Char("Name", required=True)
    app_id = fields.Char("Application ID", help="This is your unique application identifier. It's used to identify you when using Algolia's API.", required=True)
    api_key = fields.Char("Admin API Key", help="This is the ADMIN API key. This key is used to create, update and DELETE your indices. You can also use it to manage your API keys.", required=True)
    search_key = fields.Char("Search Key")
    validated = fields.Selection(selection=[
            ('draft', 'Draft'),
            ('validated', 'Validated'),
        ], string='Status', required=True, readonly=True, copy=False, tracking=True, default='draft')
    _sql_constraints = [
        ('unique_con_algolia_app', 'unique(app_id)', 'App already exists'),
    ]

    @api.onchange('app_id', 'api_key')
    def _on_change_fields(self):
        self.validated = "draft"
        self.search_key = False

    def api_validation(self):
        try:
            client = SearchClient.create(self.app_id, self.api_key)
            api_keys = client.list_api_keys()
            for pvalue in api_keys['keys']:
                if "Search" in pvalue['description']:
                    self.search_key = pvalue['value'] or ""

            if api_keys:
                self.validated = "validated"

        except Exception as err:
            raise UserError("Check your api credentials")

class Website(models.Model):
    _inherit = 'website'

    enable_alogolia_search = fields.Boolean("Enable Algolia Search")
    algolia_app_id = fields.Many2one('algolia.search.app', domain="[('validated', '=', 'validated')]")
    model = fields.Many2one('ir.model', default=lambda self: self.env['ir.model']._get_id('product.template'))
    custom_fields = fields.Many2many('ir.model.fields', help="Add fields which can be useful to search products on website")
    algolia_pricelist_id = fields.Many2one('product.pricelist', string='Pricelist')

    def update_index(self):
        try:
            client = SearchClient.create(self.algolia_app_id.app_id, self.algolia_app_id.api_key)
            index = client.init_index(self.name)
            index.delete()

            records = []
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            currency = self.algolia_pricelist_id.currency_id.symbol
            currency_position = self.algolia_pricelist_id.currency_id.position
            for product in self.env['product.template'].with_context(website_id=self.id).search(['&',('website_ids', 'in', self.id), ('is_published', '=', True)]):
                product_info = product._get_combination_info(pricelist=self.algolia_pricelist_id)
                obj = { 'objectID': product.id,
                        'name': product.name or "",
                        'has_discounted_price': product_info['has_discounted_price'],
                        'price': round(product_info['price'],2) or  "0.0",
                        'list_price' : round(product_info['list_price'],2) or  "0.0",
                        'imageURL': f'{self.domain or base_url}/web/image/product.template/{product.id}/image_256',
                        'src_image': f'/web/image/product.template/{product.id}/image_256',
                        'currency': currency,
                        'currency_position': currency_position,
                        'product_url': product.website_url
                    }

                for field in self.custom_fields:
                    if field.ttype == 'many2one':
                        obj[field.name] = product[field.name].name or ""
                    else:
                        obj[field.name] = product[field.name] or ""

                records.append(obj)
            
            index.save_objects(records)
            search_fields  = [field.name for field in self.custom_fields]
            index.set_settings({"searchableAttributes": ['name', 'list_price', *search_fields]}, {'forwardToReplicas': True})
           
        except Exception as err:
            raise Warning("Connection to Algolia failed! \n {0}".format(str(err)))

    def update_index_all(self):
        for website in self.search([]):
            try:
                client = SearchClient.create(website.algolia_app_id.app_id, website.algolia_app_id.api_key)
                index = client.init_index(website.name)
                index.delete()

                records = []
                base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                currency = website.algolia_pricelist_id.currency_id.symbol
                currency_position = website.algolia_pricelist_id.currency_id.position
                for product in self.env['product.template'].with_context(website_id=website.id).search(['&',('website_ids', 'in', website.id), ('is_published', '=', True)]):
                    product_info = product._get_combination_info(pricelist=website.algolia_pricelist_id)
                    obj = { 
                        'objectID': product.id,
                        'name': product.name or "",
                        'has_discounted_price': product_info['has_discounted_price'],
                        'price': round(product_info['price'],2) or  "0.0",
                        'list_price' : round(product_info['list_price'],2) or  "0.0",
                        'imageURL': f'{website.domain or base_url}/web/image/product.template/{product.id}/image_256',
                        'src_image': f'/web/image/product.template/{product.id}/image_256',
                        'currency': currency,
                        'currency_position': currency_position,
                        'product_url': product.website_url
                    }

                    for field in website.custom_fields:
                        if field.ttype == 'many2one':
                            obj[field.name] = product[field.name].name or ""
                        else:
                            obj[field.name] = product[field.name] or ""

                    records.append(obj)
                
                index.save_objects(records)
                search_fields  = [field.name for field in website.custom_fields]
                index.set_settings({"searchableAttributes": ['name', 'list_price', *search_fields]}, {'forwardToReplicas': True})
            
            except Exception as err:
                raise Warning("Connection to Algolia failed! \n {0}".format(str(err)))