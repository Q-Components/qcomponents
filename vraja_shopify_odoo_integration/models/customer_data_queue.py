import logging
import pprint
from odoo import models, api, fields, tools
from .. import shopify
from datetime import timedelta

_logger = logging.getLogger("Customer Queue Line")


class CustomerDataQueue(models.Model):
    _name = 'customer.data.queue'
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = 'Shopify Customer Data'
    _order = 'id DESC'

    @api.depends('customer_queue_line_ids.state')
    def _compute_customer_queue_line_state_and_count(self):
        for queue in self:
            queue_line_ids = queue.customer_queue_line_ids
            if all(line.state == 'draft' for line in queue_line_ids):
                queue.state = 'draft'
            elif all(line.state == 'failed' for line in queue_line_ids):
                queue.state = 'failed'
            elif all(line.state == 'completed' for line in queue_line_ids):
                queue.state = 'completed'
            else:
                queue.state = 'partially_completed'

    name = fields.Char(size=120, readonly=True, )
    instance_id = fields.Many2one("shopify.instance.integration", string="Instance")
    state = fields.Selection([("draft", "Draft"), ("partially_completed", "Partially Completed"),
                              ("completed", "Completed"), ("failed", "Failed")],
                             default="draft", store=True, compute="_compute_customer_queue_line_state_and_count")
    customer_queue_line_ids = fields.One2many("customer.data.queue.line",
                                              "customer_queue_id", "Customers")
    queue_process_count = fields.Integer(help="It is used for know, how many time queue is processed.")
    shopify_log_id = fields.Many2one('shopify.log', string="Logs")

    @api.model
    def create(self, vals):
        sequence = self.env.ref("vraja_shopify_odoo_integration.seq_shopify_customer_queue")
        name = sequence and sequence.next_by_id() or '/'
        if type(vals) == dict:
            vals.update({'name': name})
        return super(CustomerDataQueue, self).create(vals)

    def unlink(self):
        """
        This method is used for unlink queue lines when deleting main queue
        """
        for queue in self:
            if queue.customer_queue_line_ids:
                queue.customer_queue_line_ids.unlink()
        return super(CustomerDataQueue, self).unlink()

    def generate_shopify_customer_queue(self, instance):
        queue_id = self.create({
            'instance_id': instance.id,
        })
        return queue_id

    def create_shopify_customer_queue_job(self, instance_id, shopify_customer_list):
        """This method used to create a customer queue """
        res_id_list = []
        batch_size = 50
        for shopify_customer in tools.split_every(batch_size, shopify_customer_list):
            queue_id = self.env['customer.data.queue'].generate_shopify_customer_queue(instance_id)
            for customer in shopify_customer:
                shopify_customer_dict = customer.to_dict()
                self.env['customer.data.queue.line'].create_shopify_customer_queue_line(shopify_customer_dict,
                                                                                        instance_id, queue_id)
            res_id_list.append(queue_id.id)
        return res_id_list

    def fetch_customers_from_shopify_to_odoo(self, from_date, to_date):
        """This method used to fetch a shopify customer"""
        shopify_customer_list = []
        try:
            shopify_customer_list = shopify.Customer().find(processed_at_min=from_date, processed_at_max=to_date,
                                                            limit=250)
            _logger.info(shopify_customer_list)
        except Exception as error:
            _logger.info("Getting Some Error In Fetch The customer :: {0}".format(error))
        return shopify_customer_list

    def import_customers_from_shopify_to_odoo(self, instance, from_date=False, to_date=False):
        """
        This method use for import customer shopipy to odoo
        """
        instance.test_shopify_connection()
        from_date = fields.Datetime.now() - timedelta(10) if not from_date else from_date
        to_date = fields.Datetime.now() if not to_date else to_date
        shopify_customer_list = self.fetch_customers_from_shopify_to_odoo(from_date, to_date)
        if shopify_customer_list:
            res_id_list = self.create_shopify_customer_queue_job(instance, shopify_customer_list)
            instance.last_synced_customer_date = to_date
            return res_id_list

    def process_shopify_customer_queue(self):
        """
        This method is used for Create Customer from Shopify To Odoo
        From customer queue create customer in odoo
        """
        instance_id = self.instance_id
        draft_customer_queue_line_ids = self.customer_queue_line_ids.filtered(
            lambda x: x.state in ['draft'])
        if not self.shopify_log_id:
            log_id = self.env['shopify.log'].generate_shopify_logs('customer', 'import', instance_id, 'Process Started')
        else:
            log_id = self.shopify_log_id
        for customer_line in draft_customer_queue_line_ids:
            try:
                customer_id = self.env['res.partner'].create_update_customer_shopify_to_odoo(instance_id, customer_line,
                                                                                             log_id=log_id)

            except Exception as error:
                customer_line.state = 'failed'
                error_msg = '{0} - Getting Some Error When Try To Process Customer Queue From Shopify To Odoo'.format(
                    customer_line.name)
                self.env['shopify.log.line'].generate_shopify_process_line('customer', 'import', instance_id, error_msg,
                                                                           False, error, log_id, True)
                _logger.info(error)
        self.shopify_log_id = log_id.id
        log_id.shopify_operation_message = 'Process Has Been Finished'
        if not log_id.shopify_operation_line_ids:
            log_id.unlink()

class CustomerDataQueueLine(models.Model):
    _name = 'customer.data.queue.line'
    _description = 'Customer Data Line'

    name = fields.Char(string='Customer')
    instance_id = fields.Many2one('shopify.instance.integration', string='Instance', help='Select Instance Id',
                                  copy=False)
    customer_id = fields.Char(string="Customer ID", help='This is the Customer Id of Shopify customer',
                              copy=False)
    state = fields.Selection([('draft', 'Draft'), ('partially_completed', 'Partially Completed'),
                              ('completed', 'Completed'), ('failed', 'Failed')], tracking=True,
                             default='draft', copy=False)
    customer_data_to_process = fields.Text(string="customer Data", copy=False)
    customer_queue_id = fields.Many2one('customer.data.queue', string='Customer Queue')
    res_partner_id = fields.Many2one("res.partner")

    def create_shopify_customer_queue_line(self, shopify_customer_dict, instance_id, queue_id):
        """This method used to create a shopify customer queue  line """
        name = "%s %s" % (shopify_customer_dict.get('first_name') or "", (shopify_customer_dict.get('last_name') or ""))
        customer_queue_line_id = self.create({
            'customer_id': shopify_customer_dict.get('id'),
            'state': 'draft',
            'name': name.strip(),
            'customer_data_to_process': pprint.pformat(shopify_customer_dict),
            'instance_id': instance_id and instance_id.id or False,
            'customer_queue_id': queue_id and queue_id.id or False,
        })
        return customer_queue_line_id
