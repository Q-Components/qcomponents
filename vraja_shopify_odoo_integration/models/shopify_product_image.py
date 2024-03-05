# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

import base64
import logging
import hashlib
import requests
import urllib.parse
from odoo import models, fields, api, _
from odoo.tools.mimetypes import guess_mimetype

_logger = logging.getLogger("Shopify_Product_Image")


class ShopifyProductImage(models.Model):
    _name = "shopify.product.image"
    _description = "Shopify Product Image"
    _order = "sequence, create_date desc, id"

    @api.depends('image')
    def compute_image_hexdigest(self):
        for record in self:
            record.image_hex = hashlib.md5(record.image).hexdigest() if record.image else False

    image_hex = fields.Char('Image Hex', compute='compute_image_hexdigest', store=True,
                            help="Use This Field To Identify the Duplicate Image")
    name = fields.Char()
    image = fields.Binary('Image', attachment=True)
    url = fields.Char(string="Image URL")
    sequence = fields.Integer(help="Sequence of images.", index=True, default=10)
    shopify_image_id = fields.Char(string="Shopify Image ID")
    shopify_listing_id = fields.Many2one("shopify.product.listing")
    shopify_instance_id = fields.Many2one('shopify.instance.integration', string='Marketplace',
                                          related='shopify_listing_id.shopify_instance_id', store=True)
    listing_item_ids = fields.Many2many('shopify.product.listing.item', 'shopify_product_image_listing_item_rel',
                                        'shopify_image_id', 'listing_item_id', string="Listing Item")

    @api.onchange('url')
    def _onchange_url(self):
        if not self.url:
            self.image = False
            return {}
        image_types = ["image/jpeg", "image/png", "image/tiff", "image/svg+xml", "image/gif"]
        try:
            response = requests.get(self.url, stream=True, verify=False, timeout=10)
            if response.status_code == 200:
                if response.headers["Content-Type"] in image_types:
                    image = base64.b64encode(response.content)
                    self.image = image
        except:
            self.image = False
            warning = {}
            title = _("Warning for : {}".format(self.shopify_listing_id.name))
            warning['title'] = title
            warning['message'] = "There seems to problem while fetching Image from URL"
            return {'warning': warning}
        return {}

    @api.model_create_multi
    def create(self, vals_list):
        """
        Guess the extension for a file based on its MIME type, given by type
        Using This Method Generate the Image URL
        """
        res = super(ShopifyProductImage, self).create(vals_list)
        for res in res:
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            mimetype = guess_mimetype(res.image, default='image/png')
            imgext = '.' + mimetype.split('/')[1]
            if imgext == '.svg+xml':
                imgext = '.svg'
            safe_name = urllib.parse.quote(res.name)
            url = base_url + '/shopify/product/image/{}'.format(base64.urlsafe_b64encode(
                str(res.id).encode("utf-8")).decode("utf-8"))
            if res.listing_item_ids and not res.shopify_listing_id:
                res.write({'shopify_listing_id': res.listing_item_ids.mapped('shopify_product_listing_id') and
                                                 res.listing_item_ids.mapped('shopify_product_listing_id')[
                                                     0].id or False})
            res.write({'url': url})
        return res
