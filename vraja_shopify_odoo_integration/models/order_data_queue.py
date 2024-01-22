# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
from odoo import models, fields, api
from odoo.tools.safe_eval import safe_eval
from datetime import datetime, timedelta
import logging
import pprint

_logger = logging.getLogger("Shopify Order Queue")


class OrderDataQueue(models.Model):
    _name = "order.data.queue"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Shopify Order Data Queue"
    _order = 'id DESC'

    @api.depends('shopify_order_queue_line_ids.state')
    def _compute_queue_line_state_and_count(self):
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

    @api.model
    def create(self, vals):
        sequence = self.env.ref("vraja_shopify_odoo_integration.seq_shopify_order_queue")
        name = sequence and sequence.next_by_id() or '/'
        if type(vals) == dict:
            vals.update({'name': name})
        return super(OrderDataQueue, self).create(vals)

    def unlink(self):
        """
        This method is used for unlink queue lines when deleting main queue
        """
        for queue in self:
            if queue.shopify_order_queue_line_ids:
                queue.shopify_order_queue_line_ids.unlink()
        return super(OrderDataQueue, self).unlink()

    def generate_shopify_order_queue(self, instance):
        return self.create({'instance_id': instance.id})

    def auto_import_order_from_shopify_using_cron(self,instance_id):
        instance_id = self.env['shopify.instance.integration'].browse(instance_id)
        if instance_id:
            self.env['sale.order'].import_orders_from_shopify_to_odoo(instance=instance_id,
                                                                          from_date=instance_id.last_order_synced_date)

    def auto_import_cancel_order_from_shopify_using_cron(self,instance_id):
        instance_id = self.env['shopify.instance.integration'].browse(instance_id)
        if instance_id:
            self.env['sale.order'].import_cancel_order_from_shopify_to_odoo(instance_id=instance_id)

    def process_shopify_order_queue_using_cron(self):
        """This method was used for process order data queue automatically using cron job"""
        instance_ids = self.env['shopify.instance.integration'].search([])
        if instance_ids:
            for instance_id in instance_ids:
                self.with_context(from_cron=True).process_shopify_order_queue(instance_id)

    def process_shopify_order_queue(self, instance_id=False):
        """This method was used for process the order queue line from order queue"""

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
                    order_id = sale_order_object.process_import_order_from_shopify(shopify_order_dictionary,
                                                                                   instance_id, log_id, line)
                    if not order_id:
                        line.number_of_fails += 1
                except Exception as error:
                    _logger.info(error)
            self.shopify_log_id = log_id.id
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

    def create_shopify_order_queue_line(self, order_data_id, state, name, shopify_order_dict, instance_id, queue_id):
        order_queue_line_id = self.create({
            'order_data_id': order_data_id,
            'state': state,
            'name': name.strip(),
            'order_data_to_process': pprint.pformat(shopify_order_dict),
            'instance_id': instance_id.id,
            'shopify_order_queue_id': queue_id.id
        })
        return order_queue_line_id
