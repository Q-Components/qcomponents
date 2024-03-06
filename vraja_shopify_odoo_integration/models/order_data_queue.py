from odoo import models, fields, api, tools
from odoo.tools.safe_eval import safe_eval
from datetime import timedelta
from .. import shopify
import urllib.parse as urlparse
import logging
import pprint
import re

_logger = logging.getLogger("Shopify Order Queue")


class OrderDataQueue(models.Model):
    _name = "order.data.queue"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Shopify Order Data Queue"
    _order = 'id DESC'

    @api.depends('shopify_order_queue_line_ids.state')
    def _compute_queue_line_state_and_count(self):
        """
        Compute method to set queue state automatically based on queue line states.
        """
        for queue in self:
            queue_line_ids = queue.shopify_order_queue_line_ids
            if all(line.state == 'draft' for line in queue_line_ids):
                queue.state = 'draft'
            elif all(line.state == 'failed' for line in queue_line_ids):
                queue.state = 'failed'
            elif all(line.state == 'completed' for line in queue_line_ids):
                queue.state = 'completed'
            else:
                queue.state = 'partially_completed'

    name = fields.Char(string='Name')
    instance_id = fields.Many2one('shopify.instance.integration', string='Instance', help='Select Instance Id',
                                  copy=False, tracking=True)
    state = fields.Selection([('draft', 'Draft'), ('partially_completed', 'Partially Completed'),
                              ('completed', 'Completed'), ('failed', 'Failed')], tracking=True,
                             default='draft', compute="_compute_queue_line_state_and_count", store=True)
    order_queue_line_total_record = fields.Integer(string='Total Records',
                                                   help="This Button Shows Number of Total Records")
    order_queue_line_draft_record = fields.Integer(string='Draft Records',
                                                   help="This Button Shows Number of Draft Records")
    order_queue_line_fail_record = fields.Integer(string='Fail Records',
                                                  help="This Button Shows Number of Fail Records")
    order_queue_line_done_record = fields.Integer(string='Done Records',
                                                  help="This Button Shows Number of Done Records")
    order_queue_line_cancel_record = fields.Integer(string='Cancel Records',
                                                    help="This Button Shows Number of Done Records")
    shopify_order_queue_line_ids = fields.One2many("order.data.queue.line",
                                                   "shopify_order_queue_id", string="Order Queue")
    shopify_log_id = fields.Many2one('shopify.log', string="Logs")

    @api.model_create_multi
    def create(self, vals_list):
        """
        This method is used to add sequence number in new record.
        """
        sequence = self.env.ref("vraja_shopify_odoo_integration.seq_shopify_order_queue")
        for vals in vals_list:
            name = sequence and sequence.next_by_id() or '/'
            if type(vals) == dict:
                vals.update({'name': name})
        return super(OrderDataQueue, self).create(vals_list)

    def generate_shopify_order_queue(self, instance):
        """
        This method is used to create new record of order queue.
        """
        return self.create({'instance_id': instance.id})

    def create_shopify_order_queue_job(self, instance_id, shopify_order_list):
        """
        Based on the batch size inventory queue will create.
        """
        res_id_list = []
        batch_size = 50
        shopify_orders_records = tools.split_every(batch_size, shopify_order_list)
        _logger.info("Create Order queue  :: \n {} \n shopify order list :: {}".format(shopify_orders_records,shopify_order_list))
        for shopify_orders in shopify_orders_records:
            queue_id = self.generate_shopify_order_queue(instance_id)
            for order in shopify_orders:
                _logger.info("order in shopify :: {}".format(order))
                shopify_order_dict = order.to_dict()
                self.env['order.data.queue.line'].create_shopify_order_queue_line(shopify_order_dict, instance_id,
                                                                                  queue_id)
            res_id_list.append(queue_id.id)
        return res_id_list

    def import_cancel_order_from_shopify_to_odoo(self, instance_id):
        """
        This method is used to import cancel order from shopify.
        """
        cancel_order_list, page_info = [], False
        instance_id.test_shopify_connection()
        from_date = fields.Datetime.now() - timedelta(1)
        to_date = fields.Datetime.now()

        while 1:
            if page_info:
                page_wise_order_list = shopify.Order().find(page_info=page_info, limit=250)
            else:
                page_wise_order_list = shopify.Order().find(status='cancelled', fulfillment_status='unshipped', updated_at_min=from_date, updated_at_max=to_date)
            page_url = page_wise_order_list.next_page_url
            parsed = urlparse.parse_qs(page_url)
            page_info = parsed.get('page_info', False) and parsed.get('page_info', False)[0] or False
            cancel_order_list += page_wise_order_list
            if not page_info:
                break

        if cancel_order_list:
            res_id_list = self.create_shopify_order_queue_job(instance_id, cancel_order_list)
            if res_id_list:
                return True
        else:
            return True

    def fetch_orders_from_shopify_to_odoo(self, from_date=False, to_date=False, shopify_order_id=False):
        """
        From shopify library API calls to get order response.
        """
        shopify_order_list, page_info = [], False

        # Remote IDs wise import order process
        if shopify_order_id:
            shopify_order_id = list(set(re.findall(re.compile(r"(\d+)"), shopify_order_id)))
            try:
                shopify_order_list = shopify.Order().find(status="open", ids=",".join(shopify_order_id))
                _logger.info(shopify_order_list)
            except Exception as error:
                _logger.info("Getting Some Error In Fetch The Order :: \n {}".format(error))
            return shopify_order_list

        # From and to date wise import order process
        if not shopify_order_id:
            while 1:
                if page_info:
                    page_wise_order_list = shopify.Order().find(page_info=page_info, limit=250)
                else:
                    page_wise_order_list = (
                        shopify.Order().find(status='open', fulfillment_status='unshipped', processed_at_min=from_date,
                                             processed_at_max=to_date, limit=250))
                page_url = page_wise_order_list.next_page_url
                parsed = urlparse.parse_qs(page_url)
                page_info = parsed.get('page_info', False) and parsed.get('page_info', False)[0] or False
                shopify_order_list += page_wise_order_list
                if not page_info:
                    break
        return shopify_order_list

    def import_orders_from_shopify_to_odoo(self, instance, from_date=False, to_date=False, shopify_order_ids=False):
        """
        - From operation wizard's button & from import order cron this method will call.
        - Remote IDs wise import order process
        - From and to date wise import order process
        """
        instance.test_shopify_connection()
        last_synced_date = fields.Datetime.now()
        queue_id_list = []
        from_date = from_date or (fields.Datetime.now() - timedelta(days=1))
        to_date = to_date or fields.Datetime.now()

        if shopify_order_ids:
            shopify_order_list = self.fetch_orders_from_shopify_to_odoo(shopify_order_id=shopify_order_ids)
        else:
            shopify_order_list = self.fetch_orders_from_shopify_to_odoo(from_date=from_date, to_date=to_date)

        if shopify_order_list:
            queue_id_list = self.create_shopify_order_queue_job(instance, shopify_order_list)
            if shopify_order_ids and queue_id_list:
                self.browse(queue_id_list).process_shopify_order_queue()
            if queue_id_list:
                instance.last_order_synced_date = last_synced_date
        return queue_id_list

    def auto_import_order_from_shopify_using_cron(self, instance_id):
        """
        This method is used to execute cron of import order from shopify.
        """
        instance_record = self.env['shopify.instance.integration'].browse(instance_id)
        if instance_record:
            self.import_orders_from_shopify_to_odoo(instance=instance_record,
                                                    from_date=instance_record.last_order_synced_date)
        return True

    def auto_import_cancel_order_from_shopify_using_cron(self, instance_id):
        """
        This method is used to execute cron of import cancel order from shopify.
        """
        instance_record = self.env['shopify.instance.integration'].browse(instance_id)
        if instance_record:
            self.import_cancel_order_from_shopify_to_odoo(instance_id=instance_record)
        return True

    def process_shopify_order_queue_using_cron(self):
        """
        This method is used for process order data queue automatically using cron job.
        """
        instance_ids = self.env['shopify.instance.integration'].search([])
        if instance_ids:
            for instance_id in instance_ids:
                self.with_context(from_cron=True).process_shopify_order_queue(instance_id)
        return True

    def process_shopify_order_queue(self, instance_id=False):
        """
        This method is used for process the order queue line from order queue.
        """
        sale_order_object, instance_id = self.env['sale.order'], instance_id if instance_id else self.instance_id
        if self._context.get('from_cron'):
            order_data_queues = self.search([('instance_id', '=', instance_id.id), ('state', '!=', 'completed')],
                                            order="id asc")
        else:
            order_data_queues = self
        for order_data_queue in order_data_queues:
            if order_data_queue.shopify_log_id:
                log_id = order_data_queue.shopify_log_id
            else:
                log_id = self.env['shopify.log'].generate_shopify_logs('order', 'import', instance_id,
                                                                       'Process Started')
                self._cr.commit()
            if self._context.get('from_cron'):
                order_data_queue_lines = order_data_queue.shopify_order_queue_line_ids.filtered(
                    lambda x: x.state in ['draft', 'partially_completed'])
            else:
                order_data_queue_lines = order_data_queue.shopify_order_queue_line_ids.filtered(
                    lambda x: x.state in ['draft', 'partially_completed', 'failed'] and x.number_of_fails < 3)
            for line in order_data_queue_lines:
                try:
                    shopify_order_dictionary = safe_eval(line.order_data_to_process)
                    order_id, log_msg, fault_or_not, line_state = sale_order_object.process_import_order_from_shopify(
                        shopify_order_dictionary,
                        instance_id, log_id, line)

                    if not order_id:
                        line.number_of_fails += 1
                    else:
                        line.sale_order_id = order_id.id
                    self.env['shopify.log.line'].generate_shopify_process_line('order', 'import', instance_id, log_msg,
                                                                               False, log_msg, log_id, fault_or_not)
                    line.state = line_state
                except Exception as error:
                    _logger.info(error)
                    self.env['shopify.log.line'].generate_shopify_process_line('order', 'import', instance_id, error,
                                                                               False, error, log_id, True)

                    if line:
                        line.state = 'failed'
                        line.number_of_fails += 1
            order_data_queue.shopify_log_id = log_id.id
            log_id.shopify_operation_message = 'Process Has Been Finished'
            if not log_id.shopify_operation_line_ids:
                log_id.unlink()


class OrderDataQueueLine(models.Model):
    _name = 'order.data.queue.line'
    _description = "Shopify Order Data Queue Line"
    _rec_name = 'shopify_order_queue_id'

    name = fields.Char(string='Name')
    shopify_order_queue_id = fields.Many2one('order.data.queue', string='Order Data Queue')

    instance_id = fields.Many2one('shopify.instance.integration', string='Instance', help='Select Instance Id')
    order_data_id = fields.Char(string="Order Data ID", help='This is the Order Id of Shopify Order')
    state = fields.Selection(
        [('draft', 'Draft'), ('partially_completed', 'Partially Completed'),
         ('completed', 'Completed'), ('failed', 'Failed')], tracking=True,
        default='draft')
    order_data_to_process = fields.Text(string="Order Data")
    number_of_fails = fields.Integer(string="Number of attempts",
                                     help="This field gives information regarding how many time we will try to proceed the order",
                                     copy=False)
    sale_order_id = fields.Many2one('sale.order', string="Sale Order")

    def _valid_field_parameter(self, field, name):
        return name == 'tracking' or super()._valid_field_parameter(field, name)

    def create_shopify_order_queue_line(self, shopify_order_dict, instance_id, queue_id):
        """
        From this method queue line will create.
        """
        order_queue_line_id = self.create({
            'order_data_id': shopify_order_dict.get('id', ''),
            'state': 'draft',
            'name': shopify_order_dict.get('name', '').strip(),
            'order_data_to_process': pprint.pformat(shopify_order_dict),
            'instance_id': instance_id and instance_id.id or False,
            'shopify_order_queue_id': queue_id and queue_id.id or False,
        })
        return order_queue_line_id
