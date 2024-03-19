# -*- coding: utf-8 -*-

import math
from odoo import fields, http, _
# from odoo.http import request
# from odoo.addons.website.controllers.main import Website

import base64
import datetime
import logging

from itertools import islice


import odoo
from odoo.http import request, SessionExpiredException

logger = logging.getLogger(__name__)

# Completely arbitrary limits
MAX_IMAGE_WIDTH, MAX_IMAGE_HEIGHT = IMAGE_LIMITS = (1024, 768)
LOC_PER_SITEMAP = 45000
SITEMAP_CACHE_TIME = datetime.timedelta(hours=12)

class WebsiteSale(http.Controller):

    @http.route('/quick/shop', type='http', auth="public", website=True, sitemap=True)
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

# class web_inherit(Website):
#     @http.route('/sitemap.xml', type='http', auth="public", website=True, multilang=False, sitemap=False)
#     def sitemap_xml_index(self, **kwargs):
#         logger.info("Controller Called")
#         current_website = request.website
#         Attachment = request.env['ir.attachment'].sudo()
#         View = request.env['ir.ui.view'].sudo()
#         mimetype = 'application/xml;charset=utf-8'
#         content = None
#
#         def create_sitemap(url, content):
#             return Attachment.create({
#                 'raw': content.encode(),
#                 'mimetype': mimetype,
#                 'type': 'binary',
#                 'name': url,
#                 'url': url,
#             })
#
#         dom = [('url', '=', '/sitemap-%d.xml' % current_website.id), ('type', '=', 'binary')]
#         sitemap = Attachment.search(dom, limit=1)
#         if sitemap:
#             # Check if stored version is still valid
#             create_date = fields.Datetime.from_string(sitemap.create_date)
#             delta = datetime.datetime.now() - create_date
#             if delta < SITEMAP_CACHE_TIME:
#                 content = base64.b64decode(sitemap.datas)
#
#         if not content:
#             # Remove all sitemaps in ir.attachments as we're going to regenerated them
#             dom = [('type', '=', 'binary'), '|', ('url', '=like', '/sitemap-%d-%%.xml' % current_website.id),
#                    ('url', '=', '/sitemap-%d.xml' % current_website.id)]
#             sitemaps = Attachment.search(dom)
#             sitemaps.unlink()
#
#             pages = 0
#             locs = request.website.with_user(request.website.user_id)._enumerate_pages()
#             while True:
#                 values = {
#                     'locs': islice(locs, 0, LOC_PER_SITEMAP),
#                     'url_root': request.httprequest.url_root[:-1],
#                 }
#                 logger.info("Pages :{}".format(locs))
#                 urls = View._render_template('website.sitemap_locs', values)
#                 logger.info("Values :{}".format(values))
#                 if urls.strip():
#                     content = View._render_template('website.sitemap_xml', {'content': urls})
#                     pages += 1
#                     last_sitemap = create_sitemap('/sitemap-%d-%d.xml' % (current_website.id, pages), content)
#                     request.env.cr.commit()
#                 else:
#                     break
#
#             if not pages:
#                 return request.not_found()
#             elif pages == 1:
#                 # rename the -id-page.xml => -id.xml
#                 last_sitemap.write({
#                     'url': "/sitemap-%d.xml" % current_website.id,
#                     'name': "/sitemap-%d.xml" % current_website.id,
#                 })
#             else:
#                 # TODO: in master/saas-15, move current_website_id in template directly
#                 pages_with_website = ["%d-%d" % (current_website.id, p) for p in range(1, pages + 1)]
#
#                 # Sitemaps must be split in several smaller files with a sitemap index
#                 content = View._render_template('website.sitemap_index_xml', {
#                     'pages': pages_with_website,
#                     'url_root': request.httprequest.url_root,
#                 })
#                 create_sitemap('/sitemap-%d.xml' % current_website.id, content)
#
#         return request.make_response(content, [('Content-Type', mimetype)])