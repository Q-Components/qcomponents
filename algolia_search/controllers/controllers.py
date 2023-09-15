# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class AlgoliaSearch(http.Controller):
    @http.route('/algolia_search/api', type='json', auth='public', website=True)
    def get_settings(self, website_id):
        website = request.env['website'].sudo().browse(int(website_id))
        if website and website.algolia_app_id.validated == 'validated':
            return {
                'name': website.name,
                'app_id': website.algolia_app_id.app_id,
                'search_key': website.algolia_app_id.search_key,
                'enable_alogolia_search': website.enable_alogolia_search
            }
        else:
            return False