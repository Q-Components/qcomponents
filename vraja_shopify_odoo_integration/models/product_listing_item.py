import logging
from odoo import models, fields
from .. import shopify
import urllib.parse as urlparse

_logger = logging.getLogger("Shopify Product: ")


class ShopifyProductListingItem(models.Model):
    _name = 'shopify.product.listing.item'
    _description = 'Shopify Product Listing Line'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char("Title")
    shopify_instance_id = fields.Many2one('shopify.instance.integration', string='Instance', ondelete='cascade')
    shopify_product_listing_id = fields.Many2one('shopify.product.listing', string="Product Listing")
    product_id = fields.Many2one('product.product', string='Product')
    shopify_product_variant_id = fields.Char(string='Shopify Product ID')
    product_sku = fields.Char(string='SKU')
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.company.currency_id)
    image_ids = fields.Many2many('shopify.product.image', 'shopify_product_image_listing_item_rel', 'listing_item_id',
                                 'shopify_image_id', string="Images")
    sequence = fields.Integer("Position", default=1)
    taxable = fields.Boolean(default=True)
    active = fields.Boolean(default=True)
    exported_in_shopify = fields.Boolean(default=False)
    inventory_item_id = fields.Char(string="Inventory Item ID")
    inventory_policy = fields.Selection([("continue", "Allow"), ("deny", "Denied")],
                                        string="Sale out of stock products?",
                                        default="deny",
                                        help="If true than customers are allowed to place an order for the product"
                                             "variant when it is out of stock.")
    inventory_management = fields.Selection([("shopify", "Shopify tracks this product Inventory"),
                                             ("Dont track Inventory", "Don't track Inventory")],
                                            default="shopify",
                                            help="If you select 'Shopify tracks this product Inventory' than shopify"
                                                 "tracks this product inventory.if select 'Don't track Inventory' then"
                                                 "after we can not update product stock from odoo")

    def get_all_inventory_level_from_shopify(self, instance, location_id, log_id):
        try:
            inventory_level_list_from_shopify, page_info = [], False
            while 1:
                if page_info:
                    page_wise_inventory_list = shopify.InventoryLevel().find(page_info=page_info, limit=250)
                else:
                    page_wise_inventory_list = shopify.InventoryLevel().find(
                        location_ids=location_id.shopify_location_id, limit=250)
                page_url = page_wise_inventory_list.next_page_url
                parsed = urlparse.parse_qs(page_url)
                page_info = parsed.get('page_info', False) and parsed.get('page_info', False)[0] or False
                inventory_level_list_from_shopify += page_wise_inventory_list
                if not page_info:
                    break
            return inventory_level_list_from_shopify
        except Exception as error:
            message = "Error while import stock for instance %s\nError: %s" % (
                instance.name, str(error.response.code) + " " + error.response.msg)
            self.env['shopify.log.line'].generate_shopify_process_line('inventory', 'import', instance,
                                                                       message, False, message, log_id, True)
            return False

    def create_inventory_adjustment(self, stock_inventory_array_data, location_id, auto_apply=False,
                                    name_of_inventory=""):
        """
        This method is used to create or update product inventory.
        @param stock_inventory_array_data: Dictionary with product and it's quantity. like {'product_id':Qty,
        52:20, 53:60, 89:23}
        @param location_id : Location
        @param auto_apply: Pass true if automatically apply quant.
        @param name_of_inventory: set name in inventory adjustment name
        @return: Records of quant
        """
        quant_list = self.env['stock.quant']
        if stock_inventory_array_data and location_id:
            for product_id, product_qty in stock_inventory_array_data.items():
                quant_vals = {'location_id': location_id.id,
                              'product_id': product_id,
                              'inventory_quantity': product_qty
                              }
                _logger.info("Product ID: %s and its Qty: %s" % (product_id, product_qty))
                quant_list += quant_list.with_context(inventory_mode=True).create(quant_vals)
            if auto_apply and quant_list:
                quant_list.filtered(lambda x: x.product_id.tracking not in ['lot', 'serial']).with_context(
                    inventory_name=name_of_inventory).action_apply_inventory()
        return quant_list

    def import_stock_from_shopify_to_odoo(self, instance, auto_validate_inventory_in_odoo):
        """
        This method is used to import product inventory/stock from shopify to Odoo.
        """
        location_message = []
        log_id = self.env['shopify.log'].generate_shopify_logs('inventory', 'import', instance, 'Process Started')
        product_listing_items = self.search(
            [("shopify_instance_id", "=", instance.id), ("exported_in_shopify", "=", True)])
        if product_listing_items:
            instance.test_shopify_connection()

            location_ids = self.env["shopify.location"].search(
                [("is_import_stock", "=", True), ("instance_id", "=", instance.id)])
            if not location_ids:
                message = "IMPORT STOCK: Please enable at list one Shopify Location for import stock for Locations records in shopify."
                self.env['shopify.log.line'].generate_shopify_process_line('inventory', 'import', instance, message,
                                                                           False, message, log_id, True)
                _logger.info(message)
                self._cr.commit()
                return False

            for location_id in location_ids:
                warehouse_id = location_id.warehouse_id or False
                if not warehouse_id:
                    message = "IMPORT STOCK Warehouse is not set for Shopify Location {}. Please set from Locations records in shopify.".format(
                        location_id.name)
                    location_message.append(message)
                    _logger.info(message)
                    continue

                inventory_level_list_from_shopify = self.get_all_inventory_level_from_shopify(instance, location_id,
                                                                                              log_id)
                if not inventory_level_list_from_shopify:
                    continue

                stock_inventory_array_data = {}
                product_ids_list = []
                for inventory_level in inventory_level_list_from_shopify:
                    inventory_level = inventory_level.to_dict()
                    inventory_item_id = inventory_level.get("inventory_item_id")
                    qty = inventory_level.get("available")

                    shopify_product = self.env["shopify.product.listing.item"].search(
                        [("inventory_item_id", "=", inventory_item_id), ("exported_in_shopify", "=", True),
                         ("shopify_instance_id", "=", instance.id)], limit=1)
                    if shopify_product:
                        product_id = shopify_product.product_id
                        if product_id not in product_ids_list:
                            stock_inventory_data_line = {product_id.id: qty, }
                            stock_inventory_array_data.update(stock_inventory_data_line)
                            product_ids_list.append(product_id)

                if len(stock_inventory_array_data) > 0:
                    name_of_inventory = 'Inventory For Instance "%s" And Shopify Location "%s"' % (
                        instance.name, location_id.name)
                    inventory_data = self.create_inventory_adjustment(stock_inventory_array_data,
                                                                      location_id.warehouse_id.lot_stock_id,
                                                                      auto_validate_inventory_in_odoo,
                                                                      name_of_inventory)
                    if inventory_data:
                        _logger.info("Created %s." % name_of_inventory)
            if len(location_message) > 0:
                self.env['shopify.log.line'].generate_shopify_process_line('inventory', 'import', instance,
                                                                           location_message, False, location_message,
                                                                           log_id, True)
                _logger.info(location_message)
                self._cr.commit()
                return True
        return True

    def prepare_vals_for_variation_attributes(self, result, variation):
        """
        This method is designed to construct a value for variation attributes based on the received product response.
        It takes the product response (result) and the variation details (variation) as input
        returns the constructed variation_attributes.
        """
        variation_attributes = []
        option_names = [options["name"] for options in result.get("options") if options.get("name")]
        for i in range(1, 4):
            option_value = variation.get(f"option{i}", False)
            if option_value and (option_names and option_names[i - 1]):
                variation_attributes.append({"name": option_names[i - 1], "option": option_value})

        return variation_attributes

    def prepare_template_attribute_values_ids(self, variation_attributes, product_template):
        """
        This method generates a list of template attribute value IDs.
        @return: template_attribute_value_ids
        """
        template_attribute_value_ids = []
        product_attribute_obj = self.env["product.attribute"]
        product_attribute_value_obj = self.env["product.attribute.value"]
        product_template_attribute_value_obj = self.env["product.template.attribute.value"]

        for variation_attribute in variation_attributes:
            attribute_val, attribute_name = variation_attribute.get("option"), variation_attribute.get("name")
            product_attribute = product_attribute_obj.search([("name", "=ilike", attribute_name)], limit=1)

            if product_attribute:
                product_attribute_value = product_attribute_value_obj.get_attribute_values(attribute_val,
                                                                                           product_attribute.id)
                if product_attribute_value:
                    template_attribute_value_id = product_template_attribute_value_obj.search(
                        [("product_attribute_value_id", "=", product_attribute_value[0].id),
                         ("attribute_id", "=", product_attribute.id), ("product_tmpl_id", "=", product_template.id)],
                        limit=1)
                    template_attribute_value_id and template_attribute_value_ids.append(template_attribute_value_id.id)
        return template_attribute_value_ids

    def search_odoo_product_and_set_sku_barcode(self, template_attribute_value_ids, variation, product_template):
        """
        This method searches for an Odoo product using a prepared domain and updates its SKU and barcode.
        @param: template_attribute_value_ids (record of product template attribute value IDs),
        @param: variation (response of the product variant received from the Shopify store),
        @param: product_template (record of the Odoo product template) as parameters.
        @return: odoo_product_variant
        """
        odoo_product_obj = self.env["product.product"]
        sku, barcode = variation.get("sku"), variation.get("barcode") or False

        if barcode and barcode.lower() == "false":
            barcode = False

        domain = []
        for template_attribute_value in template_attribute_value_ids:
            tpl = ("product_template_attribute_value_ids", "=", template_attribute_value)
            domain.append(tpl)
        domain.append(("product_tmpl_id", "=", product_template.id))

        odoo_product_variant = odoo_product_obj.search(domain)
        if odoo_product_variant:
            sku and odoo_product_variant.write({"default_code": sku})
            barcode and odoo_product_variant.write({"barcode": barcode})

        return odoo_product_variant

    def set_shopify_variant_sku(self, result, product_template):
        """
        This method updates the variant SKU based on the attribute and attribute value.
        @param: self, result, product_template
        @return: odoo_product_variant
        """
        odoo_product_variant = False
        for variation in result.get("variants"):
            variation_attributes = self.prepare_vals_for_variation_attributes(result, variation)
            template_attribute_value_ids = self.prepare_template_attribute_values_ids(variation_attributes,
                                                                                      product_template)
            odoo_product_variant = self.search_odoo_product_and_set_sku_barcode(template_attribute_value_ids, variation,
                                                                                product_template)
        return odoo_product_variant

    def prepare_shopify_attribute_values(self, result):
        """Prepare a list of attribute values.
        :param result: Response of the product.
        @return: attrib_line_vals (list of attribute vals)
        """
        product_attribute_obj = self.env["product.attribute"]
        product_attribute_value_obj = self.env["product.attribute.value"]
        attrib_line_vals = []
        for attrib in result.get("options"):
            attrib_name = attrib.get("name")
            attrib_values = attrib.get("values")
            attribute = product_attribute_obj.get_attribute(attrib_name, auto_create=True)[0]
            attr_val_ids = [
                product_attribute_value_obj.get_attribute_values(attr_value, attribute.id, auto_create=True)[0].id
                for attr_value in attrib_values]

            if attr_val_ids:
                attribute_line_ids_data = [0, False,
                                           {"attribute_id": attribute.id, "value_ids": [[6, False, attr_val_ids]]}]
                attrib_line_vals.append(attribute_line_ids_data)
        return attrib_line_vals

    def shopify_create_product_with_variant(self, result):
        """
        Create a product template and variant.
        :param result: Response of the product.
        """
        product_template_obj = self.env["product.template"]
        template_title = result.get("title", "")
        attrib_line_vals = self.prepare_shopify_attribute_values(result)
        if attrib_line_vals:
            template_vals = {"name": template_title,
                             "detailed_type": "product",
                             "attribute_line_ids": attrib_line_vals,
                             "invoice_policy": "order"}
            product_template = product_template_obj.create(template_vals)
            odoo_product_variant = self.set_shopify_variant_sku(result, product_template)
            if odoo_product_variant:
                return product_template
        return False

    def create_or_update_shopify_listing_item_from_odoo_product_variant(self, variant, shopify_template_id,
                                                                        shopify_instance,
                                                                        shopify_product_listing_obj):
        """ This method is used to create/update the variant in the shopify instance.
            @return: shopify_variant
        """
        shopify_variant = self.search([
            ("shopify_instance_id", "=", shopify_instance.id),
            ("product_id", "=", variant.id),
            ("shopify_product_listing_id", "=", shopify_template_id)])

        # prepare a vals for the variants.
        shopify_variant_vals = ({
            "shopify_instance_id": shopify_instance.id,
            "product_id": variant.id,
            "shopify_product_listing_id": shopify_product_listing_obj.id,
            "product_sku": variant.default_code,
            "name": variant.name,
        })
        if not shopify_variant:
            shopify_variant = self.create(shopify_variant_vals)
        else:
            shopify_variant.write(shopify_variant_vals)

        return shopify_variant

    def shopify_prepare_product_listing_items_vals(self, instance, shopify_product_listing_item, is_set_price):
        """
        This method used to prepare product listing items vals for export product listing item from
        shopify instance to shopify store.
        """
        shopify_product_listing_item_vals = {}
        if shopify_product_listing_item.shopify_product_variant_id:
            shopify_product_listing_item_vals.update({"id": shopify_product_listing_item.shopify_product_variant_id})

        if is_set_price:
            product_price = instance.price_list_id and instance.price_list_id._get_product_price(
                shopify_product_listing_item.product_id, 1.0, partner=False,
                uom_id=shopify_product_listing_item.product_id.uom_id.id)
            shopify_product_listing_item_vals.update({"price": float(product_price)})

        if instance:
            shopify_product_listing_item_vals.update({"barcode": shopify_product_listing_item.product_id.barcode or "",
                                                      "grams": int(
                                                          shopify_product_listing_item.product_id.weight * 1000),
                                                      "weight": shopify_product_listing_item.product_id.weight,
                                                      "sku": shopify_product_listing_item.product_sku,
                                                      "taxable": shopify_product_listing_item.taxable and "true" or "false",
                                                      "title": shopify_product_listing_item.name,
                                                      })
            option_index = 0
            option_index_value = ["option1", "option2", "option3"]
            attribute_value_obj = self.env["product.template.attribute.value"]
            att_values = attribute_value_obj.search(
                [("id", "in", shopify_product_listing_item.product_id.product_template_attribute_value_ids.ids)],
                order="attribute_id")
            for att_value in att_values:
                if option_index > 3:
                    continue
                shopify_product_listing_item_vals.update({option_index_value[option_index]: att_value.name})
                option_index = option_index + 1

        if shopify_product_listing_item.inventory_management == "shopify":
            shopify_product_listing_item_vals.update({"inventory_management": "shopify"})
        else:
            shopify_product_listing_item_vals.update({"inventory_management": None})

        if shopify_product_listing_item.inventory_policy == "continue":
            shopify_product_listing_item_vals.update({"inventory_policy": "continue"})
        else:
            shopify_product_listing_item_vals.update({"inventory_policy": "deny"})
        return shopify_product_listing_item_vals
