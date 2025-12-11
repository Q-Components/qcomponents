# -*- coding: utf-8 -*-
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.addons.website_sale.controllers.cart import Cart
from odoo import http
from odoo.http import request
from odoo.tools.translate import LazyTranslate, _

_lt = LazyTranslate(__name__)


class WebsiteSaleExtended(WebsiteSale):

    # @http.route(['/shop/cart/update_json'], type='json', auth="public", methods=['POST'], website=True, csrf=False)
    # def cart_update_json(self, product_id, line_id=None, add_qty=None, set_qty=None, display=True):
    #     result = super(WebsiteSaleExtended, self).cart_update_json(product_id, line_id, add_qty, set_qty, display)
    #
    #     is_min = request.website.check_cart_amount()
    #     result['website_sale.check'] = is_min
    #     return result

    @http.route(
        '/shop/checkout',
        type='http',
        auth='public',
        methods=['GET'],
        website=True,
        sitemap=False,
        list_as_website_content=_lt("Shop Checkout")
    )
    def shop_checkout(self, try_skip_step=None, **query_params):

        # your custom check
        is_min = request.website.check_cart_amount()

        if is_min:
            # call Odoo base
            return super(WebsiteSaleExtended, self).shop_checkout(
                try_skip_step=try_skip_step,
                **query_params
            )
            
        return request.redirect("/shop/cart")

    # @http.route(['/shop/checkout'], type='http', auth="public", website=True, sitemap=False)
    # def shop_checkout(self, **post):
    #     is_min = request.website.check_cart_amount()
    #     if is_min:
    #         return super(WebsiteSaleExtended, self).shop_checkout(**post)
    #     return request.redirect("/shop/cart")

    @http.route('/shop/payment', type='http', auth='public', website=True, sitemap=False)
    def shop_payment(self, **post):
        is_min = request.website.check_cart_amount()
        if is_min:
            return super(WebsiteSaleExtended, self).shop_payment(**post)
        return request.redirect("/shop/cart")


class CartExtended(Cart):

    @http.route(
        route='/shop/cart/update',
        type='jsonrpc',
        auth='public',
        methods=['POST'],
        website=True,
        sitemap=False
    )
    def update_cart(self, line_id, quantity, product_id=None, **kwargs):

        # call super from Cart, not WebsiteSale
        result = super().update_cart(
            line_id, quantity, product_id=product_id, **kwargs
        )

        is_min = request.website.check_cart_amount()
        result['website_sale_check'] = is_min
        return result