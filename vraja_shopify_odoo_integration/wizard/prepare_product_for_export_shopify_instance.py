import logging
from odoo import models, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger("Shopify")


class PrepareProductForExportOdoo(models.TransientModel):
    """
    Model for adding products into Odoo Shopify.
    """
    _name = "prepare.product.for.export.shopify.instance"
    _description = "Prepare product for export in Shopify Instance"

    shopify_instance_id = fields.Many2one("shopify.instance.integration", string="Shopify Instance")

    def prepare_product_for_export_shopify_instance(self):
        try:
            active_template_ids = self._context.get("active_ids", [])
            product_templates_ids = self.env["product.template"].browse(active_template_ids)
            product_templates = product_templates_ids.filtered(lambda template: template.detailed_type == "product")
            if not product_templates:
                raise UserError(_("It seems like selected products are not Storable products."))
            shopify_template_id = False
            product_variants_ids = product_templates.product_variant_ids
            shopify_instance = self.shopify_instance_id

            for variant in product_variants_ids:
                if not variant.default_code:
                    continue
                product_template_id = variant.product_tmpl_id
                if product_template_id.attribute_line_ids and len(product_template_id.attribute_line_ids.filtered(
                        lambda x: x.attribute_id.create_variant == "always")) > 3:
                    continue
                shopify_product_listing_obj, shopify_template_id = self.env[
                    "shopify.product.listing"].create_or_update_shopify_instance_product_template(
                    shopify_instance, product_template_id, shopify_template_id)

                self.env["shopify.product.listing.item"].create_or_update_shopify_instance_product_variant(variant,
                                                                                                           shopify_template_id,
                                                                                                           shopify_instance,
                                                                                                           shopify_product_listing_obj)

            return {
                'effect': {
                    'fadeout': 'slow',
                    'message': "Yeah! Shopify products export successfully!!",
                    'img_url': '/web/static/img/smile.svg',
                    'type': 'rainbow_man',
                }
            }
        except Exception as e:
            _logger.info("Getting an Error : {}".format(e))
