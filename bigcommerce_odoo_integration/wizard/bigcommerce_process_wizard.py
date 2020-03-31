from odoo import fields,models,api

class bigcommerceProcessWizard(models.TransientModel):
    _name="bigcommerce.process.wizard"
    _rec_name = "warehouse_id"

    warehouse_id=fields.Many2one("stock.warehouse","Warehouse")
    bigcommerce_store_id = fields.Many2one("bigcommerce.store.configuration", "bigcommerce Store")

    # Odoo To bigcommerce Export Operations
    odoo_to_bigcommerce_export_product_categories = fields.Boolean("Export Product Categories", default=False)
    odoo_to_bigcommerce_update_product_categories = fields.Boolean("Update product Categories", default=False)

    odoo_to_bigcommerce_export_products =fields.Boolean("Export Products",default=False)
    odoo_to_bigcommerce_update_products = fields.Boolean("Update Products", default=False)
    odoo_to_bigcommerce_export_product_attribute = fields.Boolean(string="Export Product Attribute",default=False)
    odoo_to_bigcommerce_export_product_variant = fields.Boolean(string="Export Product Variant",default=False)

    # bigcommerce To Odoo Import Operations
    bigcommerce_to_odoo_import_product_categories = fields.Boolean("Import Product Categories", default=False)

    bigcommerce_to_odoo_import_product_attribute = fields.Boolean(string="Import Product Attribute",default=False)    
    bigcommerce_to_odoo_import_products = fields.Boolean("Import Products", default=False)
    bigcommerce_to_odoo_import_product_variant = fields.Boolean(string="Import Product Variant",default=False)
    bigcommerce_import_product_skucode_check =  fields.Boolean(string="Import Product Using SkuCode",default=False)

    bigcommerce_to_odoo_import_customers = fields.Boolean("Import Customers", default=False)

    bigcommerce_to_odoo_import_orders = fields.Boolean("Import Orders", default=False)
    bigcommerce_to_odoo_import_inventory = fields.Boolean("Import Product Inventory", default=False)

    def bigcommerce_operations_execution_method(self):
        product_category_obj=self.env['product.category']
        product_obj=self.env['product.template']
        customer_obj = self.env['res.partner']
        product_attribute_obj = self.env['product.attribute']
        product_inventory = self.env['stock.inventory']
        sale_order_obj = self.env['sale.order']
        store_ids =self.bigcommerce_store_id if self.bigcommerce_store_id else self.warehouse_id.bigcommerce_store_ids
        # Export Product Category Operation
        if self.odoo_to_bigcommerce_export_product_categories:
            product_category_obj.odoo_to_bigcommerce_export_product_categories(self.warehouse_id,store_ids)
        if self.odoo_to_bigcommerce_export_products:
            product_obj.export_product_to_bigcommerce(self.warehouse_id,store_ids)
        if self.odoo_to_bigcommerce_export_product_attribute:
            product_attribute_obj.export_product_attribute_to_bigcommerce(self.warehouse_id,store_ids)
        if self.odoo_to_bigcommerce_export_product_variant:
            product_obj.export_product_variant_to_bigcommerce(self.warehouse_id,store_ids)

        # Import
        if self.bigcommerce_to_odoo_import_customers:
            customer_obj.bigcommerce_to_odoo_import_customers(self.warehouse_id, store_ids)
        if self.bigcommerce_to_odoo_import_product_categories:
            product_category_obj.bigcommerce_to_odoo_import_product_categories(self.warehouse_id,store_ids)
        if self.bigcommerce_to_odoo_import_products:
            product_obj.import_product_from_bigcommerce(self.warehouse_id,store_ids)
        if self.bigcommerce_to_odoo_import_product_attribute:
            product_attribute_obj.import_product_attribute_from_bigcommerce(self.warehouse_id,store_ids)
        if self.bigcommerce_to_odoo_import_orders:
            if not self.bigcommerce_to_odoo_import_customers:
                customer_obj.bigcommerce_to_odoo_import_customers(self.warehouse_id, store_ids)
            sale_order_obj.bigcommerce_to_odoo_import_orders(self.warehouse_id,store_ids)
        if self.bigcommerce_to_odoo_import_inventory:
            product_inventory.bigcommerce_to_odoo_import_inventory(self.warehouse_id,store_ids)
