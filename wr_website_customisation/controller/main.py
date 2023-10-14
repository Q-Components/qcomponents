# -*- coding: utf-8 -*-

import math
from odoo import fields, http, _
from odoo.http import request


class WebsiteSale(http.Controller):

    @http.route('/quick/shop', type='http', auth="public", website=True)
    def website_quick_shop(self, **kw):
        return request.render("wr_website_customisation.QuickShop", {})

    def get_filters_query(self, filter):
        if filter == 'featured':
            return 'ORDER BY pt.website_sequence ASC'
        if filter == 'newest_arrivals':
            return 'ORDER BY pt.create_date DESC'
        if filter == 'name_a_z':
            return 'ORDER BY pt.name ASC'
        if filter == 'price_low_high':
            return 'ORDER BY pt.list_price ASC'
        if filter == 'price_high_low':
            return 'ORDER BY pt.list_price DESC'
        return ''

    @http.route(['/fetch_quick_shop_products'], type='json', auth="public", website=True, sitemap=False)
    def fetch_quick_shop_products(self, **post):
        if 'term' in post:
            query = f"""
                select pp.id from product_product pp
                join product_template pt
                on pp.product_tmpl_id = pt.id
                where pt.sale_ok = 't'
                and pp.active = 't'
                and pt.is_published = 't'
                and (pt.website_id = {request.website.id} or pt.website_id is null )
                and (pt.name ILIKE '%{post.get('term')}%'
                or pt.x_studio_alternate_number ilike '%{post.get('term')}%'
                or pt.default_code ilike '%{post.get('term')}%') {self.get_filters_query(post.get('active_filter'))}
                limit {post.get('limit', 20)} OFFSET {post.get('offset', 0)}
            """
            request.env.cr.execute(query)
            products_ids = request.env.cr.fetchall()
            products_ids = [product[0] for product in products_ids]
            products_ids = request.env['product.product'].sudo().browse(products_ids)
            products = [{
                'id': product_id.id,
                'name': product_id.display_name,
                'x_studio_alternate_number': product_id.x_studio_alternate_number,
                'qty_available': product_id.qty_available,
                'description_sale': product_id.description_sale,
                'uom_id': [product_id.uom_id.id, product_id.uom_id.name],
                'website_url': product_id.product_tmpl_id.website_url,
                'price': product_id.lst_price,
                'virtual_available': product_id.virtual_available
            } for product_id in products_ids]
            request.env.cr.execute(f"""
                select count(pp.id) from product_product pp
                join product_template pt
                on pp.product_tmpl_id = pt.id
                where pt.sale_ok = 't'
                and pp.active = 't'
                and pt.is_published = 't'
                and (pt.website_id = {request.website.id} or pt.website_id is null )
                and (pt.name ILIKE '%{post.get('term')}%'
                or pt.x_studio_alternate_number ilike '%{post.get('term')}%'
                or pt.default_code ilike '%{post.get('term')}%')
            """)
            total_products = request.env.cr.fetchall()
            total_products = total_products[0][0]
            max_offset = math.ceil(total_products / post.get('limit') or 1)
            max_offset = (max_offset - 1) * post.get('limit')
            return {
                'success': True,
                'products': products,
                'next_offset': (post.get('offset') + post.get('limit')),
                'current_offset': post.get('offset') + 1,
                'max_offset': max_offset,
                'total_products': total_products
            }
        return {
            'success': False,
            'products': []
        }
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
