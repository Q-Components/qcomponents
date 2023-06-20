# -*- coding: utf-8 -*-
from odoo.addons.website_sale.controllers.main import WebsiteSale

from odoo import http
from odoo.http import request


class WebsiteSaleExtended(WebsiteSale):
    @http.route(['/shop/cart/update_json'], type='json', auth="public", methods=['POST'], website=True, csrf=False)
    def cart_update_json(self, product_id, line_id=None, add_qty=None, set_qty=None, display=True):
        result = super(WebsiteSaleExtended, self).cart_update_json(product_id, line_id, add_qty, set_qty, display)

        is_min = request.website.check_cart_amount()
        result['website_sale.check'] = is_min
        return result

    @http.route(['/shop/checkout'], type='http', auth="public", website=True, sitemap=False)
    def checkout(self, **post):
        is_min = request.website.check_cart_amount()
        if is_min:
            return super(WebsiteSaleExtended, self).checkout(**post)
        return request.redirect("/shop/cart")

    @http.route('/shop/payment', type='http', auth='public', website=True, sitemap=False)
    def shop_payment(self, **post):
        is_min = request.website.check_cart_amount()
        if is_min:
            return super(WebsiteSaleExtended, self).shop_payment(**post)
        return request.redirect("/shop/cart")
