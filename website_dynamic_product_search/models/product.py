# -*- coding: utf-8 -*-
from odoo import models, api


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model
    def _search_get_detail(self, website, order, options):
        res = super()._search_get_detail(website, order, options)

        for field in website.product_search_field_ids.sudo():
            field_name = field.name

            if field.model == 'product.product':
                field_name = 'product_variant_ids.%s' % field_name

            if field_name not in res['search_fields']:
                res['search_fields'].append(field_name)

            if (field.model == 'product.template' and field.ttype not in ['many2one', 'many2many'] 
                and field.name not in res['fetch_fields']):
                res['fetch_fields'].append(field.name)
                
            if field.name not in res['mapping']:
                res['mapping'][field.name] = {
                    'name': field_name,
                    'type': 'text',
                    'match': True,
                }

        return res