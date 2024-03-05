import logging
from odoo import models, fields
from odoo.exceptions import UserError
from .. import shopify

_logger = logging.getLogger("Shopify Operations")


class ExportProductToShopify(models.TransientModel):
    """
    Model for adding products into Shopify.
    """
    _name = "export.product.to.shopify"
    _description = "Export Products To Shopify"

    shopify_is_set_price = fields.Boolean(string="Set Price ?",
                                          help="If is a mark, it set the price with product in the Shopify store.",
                                          default=False)
    shopify_is_publish = fields.Selection(
        [('publish_product_web', 'Publish Web Only'), ('publish_product_global', 'Publish Web and POS'),
         ('unpublish_product', 'Unpublish')],
        string="Publish In Website ?",
        help="If is a mark, it publish the product in website.",
        default='publish_product_web')
    shopify_is_set_image = fields.Boolean(string="Set Image ?",
                                          help="If is a mark, it set the image with product in the Shopify store.",
                                          default=False)

    def manual_export_product_to_shopify(self):
        """
        This method is used to call child method for export products from shopify products listing to Shopify store.
        """
        shopify_products = self._context.get('active_ids', [])
        shopify_product_listing_obj = self.env["shopify.product.listing"].browse(shopify_products)
        shopify_product_listing_ids = shopify_product_listing_obj.filtered(lambda x: not x.exported_in_shopify)
        if shopify_product_listing_ids and len(shopify_product_listing_ids) > 80:
            raise UserError("Error:\n- System will not export more then 80 Products at a "
                            "time.\n- Please select only 80 product for export.")
        elif not shopify_product_listing_ids:
            raise UserError("All products are already exported. \nInstead of export try to update product.")
        shopify_instances = self.env['shopify.instance.integration'].search([])
        for instance in shopify_instances:
            log_id = self.env['shopify.log'].generate_shopify_logs('product', 'export', instance, 'Process Started')
            product_listing_ids = shopify_product_listing_ids.filtered(
                lambda product: product.shopify_instance_id == instance)
            if product_listing_ids:
                try:
                    instance.connect_in_shopify()
                    # Used to export the shopify product from odoo to shopify.
                    for shopify_product_listing_id in shopify_product_listing_ids:
                        new_product = shopify.Product()
                        self.env["shopify.product.listing"].prepare_shopify_product_listing_for_update_and_export(
                            new_product, shopify_product_listing_id, instance, self.shopify_is_publish,
                            self.shopify_is_set_price, log_id)
                        result = new_product.save()
                        if result:
                            message = 'Shopify Product ID : {}'.format(new_product.id)
                            self.env['shopify.log.line'].generate_shopify_process_line('product', 'export', instance,
                                                                                       message,
                                                                                       False, message, log_id, False)
                            export_product = self.env[
                                "shopify.product.listing"].update_products_listing_item_details_shopify_information(
                                new_product, shopify_product_listing_id, self.shopify_is_publish, instance, log_id)
                            if export_product:
                                message = 'Successfully Export Shopify Product : {}'.format(
                                    shopify_product_listing_id.name)
                                self.env['shopify.log.line'].generate_shopify_process_line('product', 'export',
                                                                                           instance,
                                                                                           message,
                                                                                           False, message, log_id,
                                                                                           False)
                        if self.shopify_is_set_image:
                            product_type = 'export'
                            shopify_product_listing_obj.update_shopify_product_images(log_id, instance, product_type)
                        self._cr.commit()
                except Exception as error:
                    error_msg = 'Getting some error when try to export product from odoo to shopify.'
                    self.env['shopify.log.line'].generate_shopify_process_line('Product', 'Export', instance,
                                                                               error_msg, False, error, log_id, True)
            if not log_id.shopify_operation_line_ids:
                log_id.unlink()
        return True

    def update_products_from_odoo_to_shopify_store(self):
        """
        This Method is used for update the product information from odoo to shopify store
        """
        if not self.shopify_is_set_price and not self.shopify_is_publish and not self.shopify_is_set_image:
            raise UserError("You need to select any one option for update product")

        shopify_product_listing_obj = self.env["shopify.product.listing"]
        shopify_products = self._context.get('active_ids', [])
        product_listing_records = shopify_product_listing_obj.search(
            [('id', 'in', shopify_products), ('exported_in_shopify', '=', True)])
        if product_listing_records and len(product_listing_records) > 80:
            raise UserError("Shopify not allow to update more than 80 items at a time")

        shopify_instances = self.env['shopify.instance.integration'].search([])
        for instance_id in shopify_instances:
            log_id = self.env['shopify.log'].generate_shopify_logs('product', 'update', instance_id,
                                                                   'Process Started')
            shopify_products_listing = product_listing_records.filtered(
                lambda x: x.shopify_instance_id == instance_id)
            if shopify_products_listing:
                try:
                    update_product = shopify_product_listing_obj.update_products_details_in_shopify_store(instance_id,
                                                                                                          shopify_products_listing,
                                                                                                          self.shopify_is_set_price,
                                                                                                          self.shopify_is_publish,
                                                                                                          log_id)
                    if update_product:
                        message = 'Successfully Update Shopify Product : {}'.format(shopify_products_listing.name)
                        self.env['shopify.log.line'].generate_shopify_process_line('product', 'update', instance_id,
                                                                                   message,
                                                                                   False, message, log_id, False)
                        if self.shopify_is_set_image:
                            product_type = 'update'
                            shopify_products_listing.update_shopify_product_images(log_id, instance_id, product_type)
                except Exception as error:
                    error_msg = 'Getting Some Error When Try To Export Product From Odoo To Shopify'
                    self.env['shopify.log.line'].generate_shopify_process_line('product', 'update', instance_id,
                                                                               error_msg, False, error, log_id, True)
            if not log_id.shopify_operation_line_ids:
                log_id.unlink()
        return True
