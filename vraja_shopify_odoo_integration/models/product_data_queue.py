import logging
import re
from datetime import  timedelta
from odoo import models, fields, tools, api
import pprint
from .. import shopify

_logger = logging.getLogger("Shopify Product Queue")


class ProductDataQueue(models.Model):
    _name = "product.data.queue"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Shopify Product Data Queue"
    _order = 'id DESC'

    @api.depends('shopify_product_queue_line_ids.state')
    def _compute_product_queue_line_state_and_count(self):
        for queue in self:
            queue_line_ids = queue.shopify_product_queue_line_ids
            if all(line.state == 'draft' for line in queue_line_ids):
                queue.state = 'draft'
            elif all(line.state == 'failed' for line in queue_line_ids):
                queue.state = 'failed'
            elif all(line.state == 'completed' for line in queue_line_ids):
                queue.state = 'completed'
            else:
                queue.state = 'partially_completed'

    name = fields.Char(string='Name')
    instance_id = fields.Many2one('shopify.instance.integration', string='Instance', help='Select Instance Id')
    state = fields.Selection(selection=[('draft', 'Draft'), ('partially_completed', 'Partially Completed'),
                                        ('completed', 'Completed'), ('failed', 'Failed')],
                             tracking=True, default='draft', compute="_compute_product_queue_line_state_and_count")
    product_queue_line_total_record = fields.Integer(string='Total Records',
                                                     help="This Button Shows Number of Total Records")
    product_queue_line_draft_record = fields.Integer(string='Draft Records',
                                                     help="This Button Shows Number of Draft Records")
    product_queue_line_fail_record = fields.Integer(string='Fail Records',
                                                    help="This Button Shows Number of Fail Records")
    product_queue_line_done_record = fields.Integer(string='Done Records',
                                                    help="This Button Shows Number of Done Records")
    product_queue_line_cancel_record = fields.Integer(string='Cancel Records',
                                                      help="This Button Shows Number of Done Records")
    shopify_product_queue_line_ids = fields.One2many("product.data.queue.line",
                                                     "shopify_product_queue_id", "Product Queue Lines")
    shopify_log_id = fields.Many2one('shopify.log', string="Logs")

    @api.model
    def create(self, vals):
        sequence = self.env.ref("vraja_shopify_odoo_integration.seq_product_queue")
        name = sequence and sequence.next_by_id() or '/'
        if type(vals) == dict:
            vals.update({'name': name})
        return super(ProductDataQueue, self).create(vals)

    def unlink(self):
        """
        This method is used for unlink queue lines when deleting main queue
        """
        for queue in self:
            if queue.shopify_product_queue_line_ids:
                queue.shopify_product_queue_line_ids.unlink()
        return super(ProductDataQueue, self).unlink()

    def generate_shopify_product_queue(self, instance):
        return self.create({'instance_id': instance.id})

    def create_shopify_product_queue_job(self, instance_id, shopify_product_list):
        """
        Based on the batch size product queue will create.
        """
        queue_id_list = []
        batch_size = 50
        for shopify_products in tools.split_every(batch_size, shopify_product_list):
            queue_id = self.generate_shopify_product_queue(instance_id)
            for product in shopify_products:
                shopify_product_dict = product.to_dict()
                self.env['product.data.queue.line'].create_shopify_product_queue_line(shopify_product_dict, instance_id,
                                                                                      queue_id)
            queue_id_list.append(queue_id.id)
        return queue_id_list

    def fetch_product_from_shopify_to_odoo(self, from_date=False, to_date=False, shopify_product_ids=False):
        """
        From shopify library API calls to get product response.
        """
        shopify_product_list = []
        if shopify_product_ids:
            template_ids = list(set(re.findall(re.compile(r"(\d+)"), shopify_product_ids)))
            try:
                shopify_product_list = shopify.Product().find(ids=",".join(template_ids))
                _logger.info(shopify_product_list)
            except Exception as error:
                _logger.info("Getting Some Error In Fetch The product :: \n {}".format(error))
            return shopify_product_list
        if not shopify_product_ids:
            shopify_product_list = shopify.Product().find(status='active', processed_at_min=from_date,
                                                          processed_at_max=to_date, limit=250)
        return shopify_product_list

    def import_product_from_shopify_to_odoo(self, instance, from_date=False, to_date=False, shopify_product_ids=False):
        """
        From operation wizard's button this method will call if product import option get selected.
        """
        instance.test_shopify_connection()
        queue_id_list = []
        from_date = fields.Datetime.now() - timedelta(10) if not from_date else from_date
        to_date = fields.Datetime.now() if not to_date else to_date
        last_synced_date = fields.Datetime.now()

        if shopify_product_ids:
            shopify_product_list = self.fetch_product_from_shopify_to_odoo(shopify_product_ids=shopify_product_ids)
        if not shopify_product_ids:
            shopify_product_list = self.fetch_product_from_shopify_to_odoo(from_date=from_date, to_date=to_date)
        if shopify_product_list:
            queue_id_list = self.create_shopify_product_queue_job(instance, shopify_product_list)
            if queue_id_list:
                instance.last_product_synced_date = last_synced_date
        return queue_id_list

    def process_shopify_product_queue(self):
        """
        In product queue given process button, from this button this method get executed.
        From this method from shopify product will get imported into Odoo.
        """
        shopify_product_object, instance_id = self.env['shopify.product.listing'], self.instance_id
        queue_line_ids = self.shopify_product_queue_line_ids.filtered(lambda x: x.state in ['draft', 'failed'])
        log_id = self.env['shopify.log'].generate_shopify_logs('product', 'import', instance_id, 'Process Started')
        self._cr.commit()
        commit_counter = 0
        for line in queue_line_ids:
            commit_counter += 1
            if commit_counter == 10:
                self._cr.commit()
                commit_counter = 0
            try:
                shopify_product_object.shopify_create_products(product_queue_line=line, instance=instance_id,
                                                               log_id=log_id)
            except Exception as error:
                line.state = 'failed'
                error_msg = 'Getting Some Error When Try To Process Product Queue From Shopify To Odoo'
                self.env['shopify.log.line'].generate_shopify_process_line('product', 'import', instance_id, error_msg,
                                                                           False, error, log_id, True)
                _logger.info(error)
        self.shopify_log_id = log_id.id
        log_id.shopify_operation_message = 'Process Has Been Finished'
        if not log_id.shopify_operation_line_ids:
            log_id.unlink()


class ProductDataQueueLine(models.Model):
    _name = "product.data.queue.line"
    _description = "Product Data Queue Line"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string='Name')
    shopify_product_queue_id = fields.Many2one('product.data.queue', string='Product Data Queue')
    instance_id = fields.Many2one('shopify.instance.integration', string='Instance',
                                  help='Select Instance Id')
    product_data_id = fields.Char(string="Product Data ID", help='This is the Product Id of Shopify Product')
    state = fields.Selection(selection=[('draft', 'Draft'), ('partially_completed', 'Partially Completed'),
                                        ('completed', 'Completed'), ('failed', 'Failed')], default='draft')
    product_data_to_process = fields.Text(string="Product Data")

    def create_shopify_product_queue_line(self, shopify_product_dict, instance_id, queue_id):
        """
        From this method queue line will create.
        """
        product_queue_line_id = self.create({
            'product_data_id': shopify_product_dict.get('id'),
            'state': 'draft',
            'name': shopify_product_dict.get('title', '').strip(),
            'product_data_to_process': pprint.pformat(shopify_product_dict),
            'instance_id': instance_id and instance_id.id or False,
            'shopify_product_queue_id': queue_id and queue_id.id or False,
        })
        return product_queue_line_id
