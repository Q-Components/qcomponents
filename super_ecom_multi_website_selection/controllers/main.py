import io
import json
import operator

from odoo.addons.website_sale.controllers.main import WebsiteSale

from odoo import http
from odoo.http import request
from odoo.http import content_disposition,request
from odoo.osv import expression

class website_sale(WebsiteSale):
    
    @http.route()
    def shop(self, page=0, category=None, search='', ppg=False, **post):
        res = super(website_sale, self).shop(page, category, search, ppg, **post)
        request.env['website'].search_count([])
        res.qcontext['website'] = request.website
        return res