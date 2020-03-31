import json
from requests import request
from threading import Thread
from odoo import fields,models,api,_, registry, SUPERUSER_ID
import logging
from datetime import datetime, timedelta
_logger = logging.getLogger("BigCommerce")

class BigCommerceStoreConfiguration(models.Model):
    _name = "bigcommerce.store.configuration"
    _description = 'BigCommerce Store Configuration'

    name = fields.Char(required=True,string="Name")
    active = fields.Boolean('Active', default=True)
    bigcommerce_store_hash=fields.Char(string="Store Hash")
    bigcommerce_x_auth_client = fields.Char(string="X-Auth-Client", help="X-Auth-Client",copy=False)
    bigcommerce_x_auth_token = fields.Char(copy=False,string='X-Auth-Token', help="X-Auth-Token")
    bigcommerce_api_url = fields.Char(copy=False,string='API URL', help="API URL, Redirect to this URL when calling the API.",default="https://api.bigcommerce.com/stores/")
    bigcommerce_order_status = fields.Selection([('0', '0 - Incomplete'),
                                              ('1', '1 - Pending'),
                                              ('2', '2 - Shipped'),
                                              ('3','3 - Partially Shipped'),
                                              ('4', '4 - Refunded'),
                                              ('5', '5 - Cancelled'),
                                              ('6', '6 - Declined'),
                                              ('7', '7 - Awaiting Payment'),
                                              ('8', '8 - Awaiting Pickup'),
                                              ('9', '9 - Awaiting Shipment'),
                                              ('10', '10 - Completed'),
                                              ('11', '11 - Awaiting Fulfillment'),
                                              ('12', '12 - Manual Verification Required'),
                                              ('13', '13 - Disputed'),
                                              ('14', '14 - Partially Refunded')],default='11')
    last_modification_date = fields.Datetime(string="Last Modification Date")
    bigcommerce_operation_message = fields.Char(string="Bigcommerce Message", help="bigcommerce_operation_message", copy=False)
    bigcommerce_product_import_status = fields.Char(string="Product Import Message", help="show status of import product process", copy=False)
    warehouse_id = fields.Many2one("stock.warehouse", "Warehouse")
    bigcommerce_product_skucode = fields.Boolean("Check Bigcommerce Product Skucode")
    source_of_import_data = fields.Integer(string="Source(Page) Of Import Data",default=1)
    destination_of_import_data = fields.Integer(string="Destination(Page) Of Import Data",default=1)

    def send_request_from_odoo_to_bigcommerce(self, body=False,api_operation=False):
        headers = {"Accept": "application/json",
                   "X-Auth-Client": "{}".format(self.bigcommerce_x_auth_client),
                   "X-Auth-Token":"{}".format(self.bigcommerce_x_auth_token),
                   "Content-Type": "application/json"}
        data = json.dumps(body)
        url="{0}{1}{2}".format(self.bigcommerce_api_url,self.bigcommerce_store_hash,api_operation)
        try:
            _logger.info("Send POST Request From odoo to BigCommerce: {0}".format(url))
            return request(method='POST', url=url, data=data, headers=headers)
        except Exception as e:
            _logger.info("Getting an Error in POST Req odoo to BigCommerce: {0}".format(e))
            return e

    def send_get_request_from_odoo_to_bigcommerce(self,api_operation=False):
        headers = {"Accept": "application/json",
                   "X-Auth-Client": "{}".format(self.bigcommerce_x_auth_client),
                   "X-Auth-Token": "{}".format (self.bigcommerce_x_auth_token),
                   "Content-Type": "application/json"}
        #
        url = "{0}{1}{2}".format(self.bigcommerce_api_url ,self.bigcommerce_store_hash, api_operation)
        try:
            _logger.info("Send GET Request From odoo to BigCommerce: {0}".format(url))
            return request(method='GET', url=url, headers=headers)            
        except Exception as e:
            _logger.info("Getting an Error in GET Req odoo to BigCommerce: {0}".format(e))
            return e


    def odoo_to_bigcommerce_export_product_categories_main(self):
        product_category_obj = self.env['product.category']
        import_categorires = product_category_obj.odoo_to_bigcommerce_export_product_categories(self.warehouse_id,self)
        return import_categorires

    def export_product_to_bigcommerce_main(self):
        product_obj = self.env['product.template']
        export_product =product_obj.export_product_to_bigcommerce(self.warehouse_id, self)
        return export_product

    def export_product_attribute_to_bigcommerce_main(self):
        product_attribute_obj = self.env['product.attribute']
        export_attribute =product_attribute_obj.export_product_attribute_to_bigcommerce(self.warehouse_id,self)
        return export_attribute

    def export_product_variant_to_bigcommerce_main(self):
        product_obj = self.env['product.template']
        export_variant = product_obj.export_product_variant_to_bigcommerce(self.warehouse_id, self)
        return export_variant

    def bigcommerce_to_odoo_import_product_categories_main(self):
        self.bigcommerce_operation_message = "Import Product Categories Process Running..."
        self._cr.commit()
        dbname = self.env.cr.dbname
        db_registry = registry(dbname)
        with api.Environment.manage(), db_registry.cursor() as cr:
            env_thread1 = api.Environment(cr, SUPERUSER_ID, self._context)
            t = Thread(target=self.bigcommerce_to_odoo_import_product_categories, args=())
            t.start()

    def bigcommerce_to_odoo_import_product_categories(self):
        with api.Environment.manage():
            new_cr = registry(self._cr.dbname).cursor()
            self = self.with_env(self.env(cr=new_cr))
            product_category_obj = self.env['product.category']
            import_categories = product_category_obj.bigcommerce_to_odoo_import_product_categories(self.warehouse_id,
                                                                                                   self)
            return import_categories
    
    def import_product_from_bigcommerce_main(self):
        self.bigcommerce_product_import_status = "Import Product Process Running..."
        self._cr.commit()
        dbname = self.env.cr.dbname
        db_registry = registry(dbname)
        with api.Environment.manage(), db_registry.cursor() as cr:
            env_thread1 = api.Environment(cr, SUPERUSER_ID, self._context)
            t = Thread(target=self.import_product_from_bigcommerce, args=())
            t.start()

    def import_product_from_bigcommerce(self):
        with api.Environment.manage():
            new_cr = registry(self._cr.dbname).cursor()
            self = self.with_env(self.env(cr=new_cr))
            product_obj = self.env['product.template']
            import_product = product_obj.import_product_from_bigcommerce(self.warehouse_id,self)
            return import_product
    
    def auto_update_pages_for_import_product(self):
        _logger.info("CRON JOB Started: {0}".format(datetime.now()))
        store_ids = self.env['bigcommerce.store.configuration'].search([])
        product_obj = self.env['product.template']
        for store in store_ids:
            if store.bigcommerce_product_import_status == "Import Product Process Completed.":
                source_page = store.source_of_import_data
                destination_page = store.destination_of_import_data
                store.source_of_import_data = destination_page + 1
                store.destination_of_import_data = destination_page + 20
                self._cr.commit()
                _logger.info("CRON JOB Enter in Product Import Method ")
                product_obj.with_user(1).import_product_from_bigcommerce(store.warehouse_id,store)
                self._cr.commit()

    def import_product_attribute_from_bigcommerce_main(self):
        product_attribute_obj = self.env['product.attribute']
        import_attribute =product_attribute_obj.import_product_attribute_from_bigcommerce(self.warehouse_id,self)
        return import_attribute

    def bigcommerce_to_odoo_import_customers_main(self):
        self.bigcommerce_operation_message = "Import Customer Process Running..."
        self._cr.commit()
        dbname = self.env.cr.dbname
        db_registry = registry(dbname)
        with api.Environment.manage(), db_registry.cursor() as cr:
            env_thread1 = api.Environment(cr, SUPERUSER_ID, self._context)
            t = Thread(target=self.bigcommerce_to_odoo_import_customers, args=())
            t.start()

    def bigcommerce_to_odoo_import_customers(self):
        with api.Environment.manage():
            new_cr = registry(self._cr.dbname).cursor()
            self = self.with_env(self.env(cr=new_cr))
            customer_obj = self.env['res.partner']
            import_customer = customer_obj.bigcommerce_to_odoo_import_customers(self.warehouse_id,self)
            return import_customer

    def bigcommerce_to_odoo_import_inventory_main(self):
        product_inventory = self.env['stock.inventory']
        import_inventory =product_inventory.bigcommerce_to_odoo_import_inventory(self.warehouse_id,self)
        return import_inventory

    def bigcommerce_to_odoo_import_orders_main(self):
        self.bigcommerce_operation_message = "Import Sale Order Process Running..."
        self._cr.commit()
        dbname = self.env.cr.dbname
        db_registry = registry(dbname)
        with api.Environment.manage(), db_registry.cursor() as cr:
            env_thread1 = api.Environment(cr, SUPERUSER_ID, self._context)
            t = Thread(target=self.bigcommerce_to_odoo_import_orders, args=())
            t.start()


    def bigcommerce_to_odoo_import_orders(self):
        with api.Environment.manage():
            new_cr = registry(self._cr.dbname).cursor()
            self = self.with_env(self.env(cr=new_cr))
            sale_order_obj = self.env['sale.order']
            import_order = sale_order_obj.bigcommerce_to_odoo_import_orders(self.warehouse_id,self)
            return import_order

    def bigcommerce_to_odoo_import_product_image_main(self):
        self.bigcommerce_operation_message = "Import Product Image Process Running..."
        self._cr.commit()
        dbname = self.env.cr.dbname
        db_registry = registry(dbname)
        with api.Environment.manage(), db_registry.cursor() as cr:
            env_thread1 = api.Environment(cr, SUPERUSER_ID, self._context)
            t = Thread(target=self.bigcommerce_to_odoo_import_product_image, args=())
            t.start()

    def bigcommerce_to_odoo_import_product_image(self):
        with api.Environment.manage():
            new_cr = registry(self._cr.dbname).cursor()
            self = self.with_env(self.env(cr=new_cr))
            product_image_obj = self.env['bigcommerce.product.image']
            import_image = product_image_obj.bigcommerce_to_odoo_import_image(self.warehouse_id, self)
            return import_image

    def bigcommerce_to_odoo_import_product_variant_image_main(self):
        self.bigcommerce_operation_message = "Import Product Variant Image Process Running..."
        self._cr.commit()
        dbname = self.env.cr.dbname
        db_registry = registry(dbname)
        with api.Environment.manage(), db_registry.cursor() as cr:
            env_thread1 = api.Environment(cr, SUPERUSER_ID, self._context)
            t = Thread(target=self.bigcommerce_to_odoo_import_product_variant_image, args=())
            t.start()

    def bigcommerce_to_odoo_import_product_variant_image(self):
        with api.Environment.manage():
            new_cr = registry(self._cr.dbname).cursor()
            self = self.with_env(self.env(cr=new_cr))
            product_image_obj = self.env['bigcommerce.product.image']
            import_variant_image = product_image_obj.bigcommerce_to_odoo_import_variant_product_image(self.warehouse_id, self)
            return import_variant_image
    
    def bigcommerce_to_odoo_import_product_custom_fields(self):
        with api.Environment.manage():
            new_cr = registry(self._cr.dbname).cursor()
            self = self.with_env(self.env(cr=new_cr))
            product_obj = self.env['product.template']
            import_product_custom_fields = product_obj.import_product_custom_fields_from_bigcommerce(self)
            return import_product_custom_fields

