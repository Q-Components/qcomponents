# -*- coding: utf-8 -*-
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo import http
from odoo.http import request


class WebsiteSaleExtended(WebsiteSale):

    def _get_order(self):
        """Get current sale order for the session."""
        return request.website.get_current_website_sale_order()

    def _check_min_amount(self, order):
        """Return True if order meets minimum amount, else False."""
        MIN_AMOUNT = 100  # Replace with your minimum cart amount
        return order and order.amount_total >= MIN_AMOUNT

    @http.route(['/shop/cart/update_json'], type='json', auth="public", methods=['POST'], website=True, csrf=False)
    def cart_update_json(self, product_id, line_id=None, add_qty=None, set_qty=None, display=True):
        result = super().cart_update_json(product_id, line_id, add_qty, set_qty, display)
        order = self._get_order()
        result['website_sale.check'] = self._check_min_amount(order)
        return result

    @http.route(['/shop/checkout'], type='http', auth="public", website=True, sitemap=False)
    def checkout(self, **post):
        order = self._get_order()
        if self._check_min_amount(order):
            return super().checkout(**post)
        return request.redirect("/shop/cart")

    @http.route('/shop/payment', type='http', auth='public', website=True, sitemap=False)
    def shop_payment(self, **post):
        order = self._get_order()
        if self._check_min_amount(order):
            return super().shop_payment(**post)
        return request.redirect("/shop/cart")
