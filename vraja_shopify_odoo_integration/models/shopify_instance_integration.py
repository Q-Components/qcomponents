from odoo import models, fields, _, api
from .. import shopify
from datetime import datetime, timedelta
from ..shopify.pyactiveresource.connection import ForbiddenAccess, ClientError
from odoo.exceptions import UserError, ValidationError
import json
import logging

_logger = logging.getLogger("Shopify: ")


class ShopifyInstanceIntegrations(models.Model):
    _name = 'shopify.instance.integration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Shopify Instance Integration'

    name = fields.Char(string='Name', help='Enter Instance Name', copy=False, tracking=True)
    active = fields.Boolean(string='Active', copy=False, tracking=True, default=True)
    company_id = fields.Many2one('res.company', string='Company', help='Select Company',
                                 copy=False, tracking=True, default=lambda self: self.env.user.company_id)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', help='Select Warehouse',
                                   copy=False, tracking=True)
    shopify_store_time_zone = fields.Char(string='Shopify Store Time Zone',
                                          help='This field used to import order process', copy=False)
    last_order_synced_date = fields.Datetime(string="Last Order Synced Date", copy=False, tracking=True)
    last_product_synced_date = fields.Datetime(string="Last Product Synced Date", copy=False, tracking=True)
    last_synced_customer_date = fields.Datetime(string='Last Customer Synced Date', copy=False, tracking=True)
    last_synced_inventory_date = fields.Datetime(string='Last Inventory Synced Date', copy=False, tracking=True)
    shopify_url = fields.Char(string='Shopify Url', help='Enter Shopify Url', copy=False, tracking=True)
    shopify_api_key = fields.Char(string='Shopify API Key', help='Enter Shopify API Key', copy=False, tracking=True)
    shopify_pwd = fields.Char(string='Shopify Password', help='Enter Shopify Password', copy=False, tracking=True)
    shopify_secret_key = fields.Char(string='Shopify Secret Key', help='Enter Shopify Secret Key', copy=False,
                                     tracking=True)
    price_list_id = fields.Many2one('product.pricelist', string="Price List", copy=False, tracking=True)
    image = fields.Binary(string="Image", help="Select Image.")
    create_product_if_not_found = fields.Boolean('Create Product in Odoo if not matched.')
    is_sync_images = fields.Boolean("Sync Product Images?",
                                    help="If true then Images will be sync at the time of Import Products.")

    shopify_discount_product_id = fields.Many2one('product.product', string="Shopify Discount Product",
                                                  copy=False, tracking=True, default=lambda self: self.env.ref(
            'vraja_shopify_odoo_integration.discount_product', False),
                                                  help="this product will be considered as a discount product for add \n"
                                                       "sale order line with discount value")
    shopify_gift_product_id = fields.Many2one('product.product', string="Shopify Gift Product",
                                              copy=False, tracking=True,
                                              default=lambda self: self.env.ref(
                                                  'vraja_shopify_odoo_integration.gift_card_product', False),
                                              help="this product will be considered as a gift product for add \n"
                                                   "sale order line")
    shopify_shipping_product_id = fields.Many2one('product.product', string="Shopify Shipping Product",
                                                  copy=False, tracking=True,
                                                  default=lambda self: self.env.ref(
                                                      'vraja_shopify_odoo_integration.shipping_product', False),
                                                  help="this product will be considered as a Shipping product for add \n"
                                                       "sale order line")
    apply_tax_in_order = fields.Selection(
        [("odoo_tax", "Odoo Default Tax Behaviour"), ("create_shopify_tax",
                                                      "Create new tax If Not Found")], default='odoo_tax',
        copy=False, help=""" For Shopify Orders :- \n
                        1) Odoo Default Tax Behaviour - The Taxes will be set based on Odoo's
                                     default functional behaviour i.e. based on Odoo's Tax and Fiscal Position configurations. \n
                        2) Create New Tax If Not Found - System will search the tax data received 
                        from Shopify in Odoo, will create a new one if it fails in finding it.""")

    auto_fulfilled_gif_card_order = fields.Boolean(string='Auto Fulfilled Gift Card Order', default=True, tracking=True)
    notify_customer = fields.Boolean(string='Notify Customer Once Update Order Status', default=False, tracking=True)
    webhook_ids = fields.One2many("shopify.webhook", "instance_id", "Webhooks")
    shopify_invoice_instance_id = fields.Many2one('shopify.instance.integration', string="Instance", copy=False)

    def prepare_shopify_shop_url(self, host, api_key, password):
        """
        This method is used to prepare a shop URL.
        """
        if host:
            shop = host.split("//")
            if len(shop) == 2:
                shop_url = shop[0] + "//" + api_key + ":" + password + "@" + shop[1] + "/admin/api/2023-04"
            else:
                shop_url = "https://" + api_key + ":" + password + "@" + shop[0] + "/admin/api/2023-04"
            return shop_url
        else:
            raise UserError("Shopify instance credential details missing/invalid.")

    def connect_in_shopify(self):
        """
        This method used to connect with Odoo to Shopify.
        """
        api_key = self.shopify_api_key
        password = self.shopify_pwd
        shop_url = self.prepare_shopify_shop_url(self.shopify_url, api_key, password)
        shopify.ShopifyResource.set_site(shop_url)
        return True

    def test_shopify_connection(self):
        """
        This method is used to check connection for shopify.
        """
        self.connect_in_shopify()
        try:
            shop_id = shopify.Shop.current()
            return shop_id
        except ForbiddenAccess as error:
            if error.response.body:
                errors = json.loads(error.response.body.decode())
                raise UserError(_("%s\n%s\n%s" % (error.response.code, error.response.msg, errors.get("errors"))))
        except ClientError as error:
            if error.response.body:
                errors = json.loads(error.response.body.decode())
                raise UserError(_("%s\n%s\n%s" % (error.response.code, error.response.msg, errors.get("errors"))))
        except Exception as e:
            raise ValidationError(e)

    def action_test_connection(self):
        """
        This method is used to test connection for shopify with & it import payment gateway, set financial status
        & payment gateway.
        """
        shopify_location_object = self.env["shopify.location"]
        payment_gateway_object = self.env["shopify.payment.gateway"]
        financial_status_object = self.env["shopify.financial.status.configuration"]
        shop_id = self.test_shopify_connection()
        shop_detail = shop_id.to_dict()
        self.write({"shopify_store_time_zone": shop_detail.get("iana_timezone")})

        shopify_location_object.import_shopify_locations(self)
        payment_gateway_object.import_payment_gateway(self)
        financial_status_object.create_shopify_financial_status(self, "paid")

        default_location_id = shop_detail.get('primary_location_id')
        default_location = default_location_id and shopify_location_object.search(
            [('shopify_location_id', '=', default_location_id), ('instance_id', '=', self.id)]) or False
        if default_location:
            default_location.write({'is_primary_location': True})

        message = _("Connection Test Succeeded!")
        return {
            'effect': {
                'fadeout': 'slow',
                'message': message,
                'img_url': '/web/static/img/smile.svg',
                'type': 'rainbow_man',
            }
        }

    @api.model_create_multi
    def create(self, vals):
        """
        In this method auto generated cron added at the time of instance creation.
        """
        instance = super(ShopifyInstanceIntegrations, self).create(vals)
        instance.action_test_connection()
        instance.create_order_queue_of_shopify_order_in_odoo_using_cron()
        instance.create_order_queue_of_shopify_cancel_order_in_odoo_using_cron()
        instance.setup_shopify_update_order_status_cron()
        instance.setup_shopify_export_stock_cron()
        return instance

    def write(self, vals):
        """
        In this method check connection if in credentials any change.
        """
        res = super(ShopifyInstanceIntegrations, self).write(vals)
        self.test_shopify_connection()
        return res

    def action_shopify_open_instance_view_form(self):
        form_id = self.sudo().env.ref('vraja_shopify_odoo_integration.shopify_instance_integration_form')
        action = {
            'name': _('Shopify Instance'),
            'view_id': False,
            'res_model': 'shopify.instance.integration',
            'context': self._context,
            'view_mode': 'form',
            'res_id': self.id,
            'views': [(form_id.id, 'form')],
            'type': 'ir.actions.act_window',
        }
        return action

    def get_stock_updates(self):
        """
        This method is used to fetch odoo product in which last stock updated in last 3 hours.
        """
        to_date = datetime.now()
        date = to_date - timedelta(hours=3)
        query = """SELECT product_id FROM stock_move WHERE date >= %s AND
                   state IN ('partially_available', 'assigned', 'done')"""
        self.env.cr.execute(query, (date,))
        result = self.env.cr.fetchall()
        return [item[0] for item in result]

    def prepare_export_stock_data_for_shopify(self, instance):
        """
        This method if used to prepare export stock data for shopify
        """
        instance_id = self.env['shopify.instance.integration'].browse(instance)
        prepare_export_stock_data_message = []
        log_id = self.env['shopify.log'].generate_shopify_logs(shopify_operation_name='inventory',
                                                               shopify_operation_type='export',
                                                               instance=instance_id,
                                                               shopify_operation_message='Process Started')

        # Fetch odoo product in which last stock updated in last 3 hours.
        updated_odoo_product_ids = self.get_stock_updates()
        if not updated_odoo_product_ids:
            return True
        _logger.info("Odoo Products List => {}".format(updated_odoo_product_ids))

        # Fetch current instance product listing items
        product_query = """SELECT product_id,inventory_item_id
                        FROM shopify_product_listing_item
                        WHERE product_id IN %s AND shopify_instance_id = %s"""
        self.env.cr.execute(product_query, (tuple(updated_odoo_product_ids), (str(instance_id.id))))
        shopify_product_listing_items = self.env.cr.fetchall()

        # Extract product_id and inventory_item_id from the first query result
        inventory_item_mapping = {t[0]: t[1] for t in shopify_product_listing_items}
        _logger.info("Inventory Item mapping => {}".format(inventory_item_mapping))

        location_ids = self.env["shopify.location"].search([("instance_id", "=", instance_id.id)])
        if not location_ids:
            message = "Location not found for instance %s while update stock" % instance_id.name
            self.env['shopify.log.line'].generate_shopify_process_line('inventory', 'export', instance, message,
                                                                       False, message, log_id, True)
            _logger.info(message)
            self._cr.commit()
            return False

        for location_id in location_ids:
            shopify_location_warehouse = location_id.export_stock_warehouse_ids or False
            if not shopify_location_warehouse:
                message = "No Warehouse found for Export Stock in Shopify Location: %s" % location_id.name
                prepare_export_stock_data_message.append(message)
                continue

            final_product_ids = self.env['product.product'].with_context(
                warehouse=shopify_location_warehouse.ids).browse(
                list(tuple(inventory_item_mapping.keys())))

            queue_line_data = []
            for product in final_product_ids:
                if inventory_item_mapping.get(product.id):
                    actual_stock = getattr(product, 'free_qty')
                    inventory_data_to_process_vals = {
                        'inventory_item_id': int(inventory_item_mapping.get(product.id)),
                        'location_id': int(location_id.shopify_location_id),
                        'available': actual_stock
                    }
                    vals = {
                        'product_id': product.id,
                        'inventory_data_to_process': inventory_data_to_process_vals,
                    }
                    queue_line_data.append(vals)
            if queue_line_data:
                self.env['inventory.data.queue'].create_shopify_inventory_queue_job(instance_id, location_id,
                                                                                    queue_line_data, log_id)
        if len(prepare_export_stock_data_message) > 0:
            self.env['shopify.log.line'].generate_shopify_process_line('inventory', 'import', instance_id,
                                                                       prepare_export_stock_data_message, False,
                                                                       prepare_export_stock_data_message,
                                                                       log_id, True)
            _logger.info(prepare_export_stock_data_message)
            self._cr.commit()
            return True
        if not log_id.shopify_operation_line_ids:
            log_id.unlink()
        return True

    def create_cron_for_automation_task(self, cron_name, model_name, code_method, interval_number=10,
                                        interval_type='minutes', numbercall=1, nextcall_timegap_minutes=10):
        """
        This method is used for create cron record.
        """
        self.env['ir.cron'].create({
            'name': cron_name,
            'model_id': self.env['ir.model'].search([('model', '=', model_name)]).id,
            'state': 'code',
            'code': code_method,
            'interval_number': interval_number,
            'interval_type': interval_type,
            'numbercall': numbercall,
            'nextcall': datetime.now() + timedelta(minutes=nextcall_timegap_minutes),
            'doall': True,
            'shopify_instance': self.id
        })
        return True

    def search_picking_to_update_status_in_shopify(self, instance):
        SQL = """SELECT id FROM stock_picking 
                    WHERE shopify_instance_id = """ + str(instance.id) + """
                    AND updated_status_in_shopify = false
                    AND state = 'done'
                    And location_dest_id in (select id from stock_location where usage = 'customer')
                    AND is_shopify_delivery = true
                    AND is_order_cancelled_in_shopify = false
                    AND is_shopify_error = false
                    order by date
                    limit 300"""
        self.env.cr.execute(SQL)
        picking_ids = [a for (a,) in self.env.cr.fetchall()]
        picking_objs = self.env["stock.picking"].browse(picking_ids)
        return picking_objs

    def update_order_status_cron_action(self, instance):
        """
        Update order status cron process
        """
        instance_id = self.env['shopify.instance.integration'].browse(instance)
        if instance_id.state == 'confirmed':
            shopify_log_id = self.env['shopify.log'].generate_shopify_logs(shopify_operation_name='order_status',
                                                                           shopify_operation_type='export',
                                                                           instance=instance_id,
                                                                           shopify_operation_message='Process Started')
            instance_id.connect_in_shopify()
            picking_objs = self.search_picking_to_update_status_in_shopify(instance_id)
            for pick in picking_objs:
                self.env['sale.order'].update_order_status_in_shopify(shopify_instance=instance_id, picking_ids=pick,
                                                                      log_id=shopify_log_id)

    def setup_shopify_update_order_status_cron(self):
        """
        From this method update order status cron creation process declared.
        """
        cron_name = "Shopify: [{0}] Update Order Status in Shopify".format(self.name)
        model_name = 'shopify.instance.integration'
        code_method = 'model.update_order_status_cron_action({0})'.format(self.id)
        self.create_cron_for_automation_task(cron_name, model_name, code_method,
                                             interval_type='minutes', interval_number=30,
                                             numbercall=1, nextcall_timegap_minutes=20)
        return True

    def shopify_unlink_old_records_cron(self):
        """
        This method is used when unlink old records cron will execute and logs more than 30 days old will be deleted.
        """
        today_date = datetime.now().date()
        month_ago = today_date - timedelta(days=30)
        shopify_log_date = self.env['shopify.log'].search([]).filtered(lambda x: x.create_date.date() < month_ago)
        if shopify_log_date:
            shopify_log_date.unlink()
        order_data_queue = self.env['order.data.queue'].search([]).filtered(lambda x: x.create_date.date() < month_ago)
        if order_data_queue:
            order_data_queue.unlink()
        inventory_data_queue = self.env['inventory.data.queue'].search([]).filtered(
            lambda x: x.create_date.date() < month_ago)
        if inventory_data_queue:
            inventory_data_queue.unlink()

    def setup_shopify_export_stock_cron(self):
        """
        From this method export stock cron creation process declared.
        """
        cron_name = "Shopify: [{0}] Prepare export stock data for Shopify".format(self.name)
        model_name = 'shopify.instance.integration'
        code_method = 'model.prepare_export_stock_data_for_shopify({0})'.format(self.id)
        self.create_cron_for_automation_task(cron_name, model_name, code_method,
                                             interval_type='minutes', interval_number=40,
                                             numbercall=1, nextcall_timegap_minutes=20)
        return True

    def create_order_queue_of_shopify_order_in_odoo_using_cron(self):
        """
        From this method create order queue for regular order cron creation process declared.
        """
        cron_name = "Shopify: [{0}] Prepare Queue Of Order From Shopify To Odoo".format(self.name)
        model_name = 'order.data.queue'
        code_method = 'model.auto_import_order_from_shopify_using_cron({0})'.format(self.id)
        self.create_cron_for_automation_task(cron_name, model_name, code_method,
                                             interval_type='minutes', interval_number=30,
                                             numbercall=1, nextcall_timegap_minutes=20)
        return True

    def create_order_queue_of_shopify_cancel_order_in_odoo_using_cron(self):
        """
        From this method create order queue for cancel order cron creation process declared.
        """
        cron_name = "Shopify: [{0}] Prepare Queue Of Cancel Order From Shopify To Odoo".format(self.name)
        model_name = 'order.data.queue'
        code_method = 'model.auto_import_cancel_order_from_shopify_using_cron({0})'.format(self.id)
        self.create_cron_for_automation_task(cron_name, model_name, code_method,
                                             interval_type='minutes', interval_number=30,
                                             numbercall=1, nextcall_timegap_minutes=20)
        return True

    def unlink(self):
        cron_records = self.env['ir.cron'].search([('shopify_instance', 'in', self.ids)])
        if cron_records:
            cron_records.unlink()
        return super(ShopifyInstanceIntegrations, self).unlink()
