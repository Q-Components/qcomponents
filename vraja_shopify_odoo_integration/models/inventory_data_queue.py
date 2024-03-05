import logging
import requests
import json
from odoo import models, fields, tools, api
from ..shopify.pyactiveresource.connection import ClientError

_logger = logging.getLogger("Shopify Inventory Queue")


class InventoryDataQueue(models.Model):
    _name = "inventory.data.queue"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Inventory Data Queue"
    _order = 'id DESC'

    @api.depends('shopify_inventory_queue_line_ids.state')
    def _compute_queue_line_state_and_count(self):
        """
        Compute method to set queue state automatically based on queue line states.
        """
        for queue in self:
            queue_line_ids = queue.shopify_inventory_queue_line_ids
            if all(line.state == 'draft' for line in queue_line_ids):
                queue.state = 'draft'
            elif all(line.state == 'failed' for line in queue_line_ids):
                queue.state = 'failed'
            elif all(line.state == 'completed' for line in queue_line_ids):
                queue.state = 'completed'
            else:
                queue.state = 'partially_completed'

    name = fields.Char(string='Name')
    shopify_location_id = fields.Many2one('shopify.location', 'Shopify Location')
    instance_id = fields.Many2one('shopify.instance.integration', string='Instance', help='Select Instance Id')
    state = fields.Selection(selection=[('draft', 'Draft'), ('partially_completed', 'Partially Completed'),
                                        ('completed', 'Completed'), ('failed', 'Failed')],
                             tracking=True, default='draft', compute="_compute_queue_line_state_and_count")
    shopify_inventory_queue_line_ids = fields.One2many("inventory.data.queue.line",
                                                       "shopify_inventory_queue_id",
                                                       "Inventory Queue Lines")
    shopify_log_id = fields.Many2one('shopify.log', string="Logs")

    @api.model_create_multi
    def create(self, vals_list):
        """
        This method is used to add sequence number in new record.
        """
        sequence = self.env.ref("vraja_shopify_odoo_integration.seq_inventory_queue")
        for vals in vals_list:
            name = sequence and sequence.next_by_id() or '/'
            if type(vals) == dict:
                vals.update({'name': name})
        return super(InventoryDataQueue, self).create(vals_list)

    def unlink(self):
        """
        This method is used for unlink queue lines when deleting main queue.
        """
        for queue in self:
            if queue.shopify_inventory_queue_line_ids:
                queue.shopify_inventory_queue_line_ids.unlink()
        return super(InventoryDataQueue, self).unlink()

    def generate_shopify_inventory_queue(self, instance, location):
        """
        This method is used to create new record of inventory queue.
        """
        return self.create({
            'instance_id': instance.id,
            'shopify_location_id': location.id
        })

    def create_shopify_inventory_queue_job(self, instance_id, location_id, shopify_inventory_list, log_id):
        """
        Based on the batch size inventory queue will create.
        """
        queue_id_list = []
        batch_size = 50
        for shopify_inventories in tools.split_every(batch_size, shopify_inventory_list):
            queue_id = self.generate_shopify_inventory_queue(instance_id, location_id)
            for inventory in shopify_inventories:
                self.env['inventory.data.queue.line'].create_shopify_inventory_queue_line(inventory, instance_id,
                                                                                          queue_id, location_id, log_id)
            queue_id_list.append(queue_id.id)
            if not queue_id.shopify_inventory_queue_line_ids:
                queue_id.unlink()
        return queue_id_list

    def process_queue_to_export_stock(self):
        """
        In this method from queue record button clicked & export inventory from odoo to shopify.
        """
        self.export_inventory_from_odoo_to_shopify()

    def export_inventory_from_odoo_to_shopify(self):
        """
        This method is used to export inventory from odoo to shopify.
        """
        if self._context.get('from_cron'):
            process_records = self.search([('state', 'not in', ['completed', 'failed'])])
        else:
            process_records = self
        if process_records:
            for rec in process_records:
                if rec.shopify_log_id:
                    log_id = rec.shopify_log_id
                else:
                    log_id = self.env['shopify.log'].generate_shopify_logs('inventory', 'export', rec.instance_id,
                                                                           'Process Started')
                self._cr.commit()

                # API Call
                shop_url = rec.instance_id.shopify_url.replace("https://", "").replace("http://", "").replace("www.",
                                                                                                              "")
                api_key = rec.instance_id.shopify_api_key
                password = rec.instance_id.shopify_pwd
                shopify_url = f'https://{api_key}:{password}@{shop_url}/admin/api/2023-04/inventory_levels/set.json'

                if self._context.get('from_cron'):
                    product_data_queue_lines = rec.shopify_inventory_queue_line_ids.filtered(
                        lambda line: line.state == 'draft')
                else:
                    product_data_queue_lines = rec.shopify_inventory_queue_line_ids.filtered(
                        lambda x: x.state in ['draft', 'failed'] and x.number_of_fails < 3)

                for inventory_line in product_data_queue_lines:
                    response = ''
                    shopify_data = {}
                    try:
                        export_data = eval(inventory_line.inventory_data_to_process)
                        shopify_data = {
                            'inventory_item_id': export_data.get('inventory_item_id'),
                            'available': int(export_data.get('available')),
                            'location_id': export_data.get('location_id')
                        }
                        headers = {'Content-Type': 'application/json'}
                        response = requests.post(shopify_url, data=json.dumps(shopify_data), headers=headers)
                        if not response:
                            inventory_line.number_of_fails += 1
                    except ClientError as error:
                        inventory_line.state = 'failed'
                        message = "Client Error while Export stock for Product ID: %s & Product Name: '%s' for instance:" \
                                  "'%s'\nError: %s\n%s" % (
                                      inventory_line.product_id.id, inventory_line.product_id.name,
                                      rec.instance_id.name, str(error.response.code) + " " + error.response.msg,
                                      json.loads(error.response.body.decode()).get("errors")[0])
                        self.env['shopify.log.line'].generate_shopify_process_line('inventory', 'import',
                                                                                   rec.instance_id, message, False,
                                                                                   error, log_id, True)
                        _logger.info(message)
                    except Exception as error:
                        message = "Error while Export stock for Product ID: %s & Product Name: '%s' for instance: " \
                                  "'%s'\nError: %s" % (
                                      inventory_line.product_id.id, inventory_line.product_id.name,
                                      rec.instance_id.name, str(error))
                        self.env['shopify.log.line'].generate_shopify_process_line('inventory', 'import',
                                                                                   rec.instance_id, message, False,
                                                                                   error, log_id, True)
                        _logger.info(message)
                    if response and response.status_code in [200, 201]:
                        inventory_line.state = 'completed'
                        message = "Successfully updated stock for product: {}.".format(inventory_line.product_id.name)
                        fault_or_not = False
                    else:
                        _logger.info("SOME ERROR FROM  %s" % shopify_url)
                        _logger.info("RESPONSE DATA  %s" % response.text)
                        inventory_line.state = 'failed'
                        message = "Error while Export stock for Product: {}.".format(inventory_line.product_id.name)
                        fault_or_not = True
                    self.env['shopify.log.line'].generate_shopify_process_line('inventory', 'import', rec.instance_id,
                                                                               message, shopify_data, response.text,
                                                                               log_id, fault_or_not)
                rec.shopify_log_id = log_id
                log_id.shopify_operation_message = 'Process Has Been Finished'
                if not log_id.shopify_operation_line_ids:
                    log_id.unlink()
            return True


class InventoryDataQueueLine(models.Model):
    _name = "inventory.data.queue.line"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    product_id = fields.Many2one('product.product')
    shopify_inventory_queue_id = fields.Many2one('inventory.data.queue', string='Inventory Data Queue')
    instance_id = fields.Many2one('shopify.instance.integration', string='Instance',
                                  help='Select Instance Id')
    state = fields.Selection(selection=[('draft', 'Draft'), ('completed', 'Completed'), ('failed', 'Failed')],
                             default='draft')
    inventory_data_to_process = fields.Text(string="Inventory Data")
    number_of_fails = fields.Integer(string="Number of attempts",
                                     help="This field gives information regarding how many time we will try to proceed the order",
                                     copy=False)

    def create_shopify_inventory_queue_line(self, shopify_inventory_dict, instance_id, queue_id, location_id, log_id):
        """
        From this method queue line will create if not exists.
        """
        existing_queue = self.search([('product_id', '=', shopify_inventory_dict.get('product_id')),
                                      ('shopify_inventory_queue_id.shopify_location_id', '=', location_id.id),
                                      ('state', '=', 'draft')])
        if existing_queue:
            existing_queue.inventory_data_to_process = shopify_inventory_dict.get('inventory_data_to_process')
            message = "Inventory data queue line already exists with product => {}".format(
                existing_queue.product_id.name)
            self.env['shopify.log.line'].generate_shopify_process_line('inventory', 'import', instance_id,
                                                                       message, False, message, log_id, True)
            return existing_queue
        inventory_queue_line_id = self.create({
            'product_id': shopify_inventory_dict.get('product_id'),
            'state': 'draft',
            'inventory_data_to_process': shopify_inventory_dict.get('inventory_data_to_process'),
            'instance_id': instance_id and instance_id.id or False,
            'shopify_inventory_queue_id': queue_id and queue_id.id or False,
        })
        message = "New Inventory data queue line created with product => {}".format(
            inventory_queue_line_id.product_id.name)
        self.env['shopify.log.line'].generate_shopify_process_line('inventory', 'import', instance_id,
                                                                   message, False, message, log_id, False)
        return inventory_queue_line_id
