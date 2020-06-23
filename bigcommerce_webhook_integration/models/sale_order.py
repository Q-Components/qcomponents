from odoo import fields, models, api,_
import logging
import time
from datetime import datetime

_logger = logging.getLogger("oneclick_done_sale")

class SaleOrder(models.Model):
    _inherit = "sale.order"
    
    def auto_process_delivery_order(self,picking_ids):
        for pick in picking_ids:
            partners = []
            is_valid = pick.prepare_picking_for_transfer()
            if is_valid:
                pick.with_user(1).action_done()
                pick.message_post(body=_("Delivery Order Process Through OneClickSaleOrder"))
                self._cr.commit()
                group_ids = self.env.ref('bigcommerce_webhook_integration.group_bigcommerce_account_access')
                for user in group_ids.with_user(1).mapped('users'):
                    if user.partner_id.email:
                        partners.append(user.partner_id.id)
                user_id = self.env['res.users'].with_user(1).search([('login','=','quote@qcomponents.com')],limit=1)
                _logger.info("USER : {0}".format(user_id))
                email_id = self.env['mail.mail'].with_user(1).create({
                        'subject': 'Sale Order Processed:{}'.format(pick.sale_id and pick.sale_id.name),
                        'email_from': user_id.partner_id.email,
                        'recipient_ids':[(6,0,partners)],
                        'auto_delete': False,
                        'body_html': "{0} Sale Order Automatically Process".format(pick.sale_id and pick.sale_id.name),
                        'state': 'outgoing',
                        'author_id': user_id.partner_id.id,
                        'date': time.strftime('%Y-%m-%d %H:%M:%S'),
                    })
                _logger.info("Email Created : {0}".format(email_id))
                email_id.with_user(1).send()
                self._cr.commit()
            else:
                _logger.info("Need to Review Delivery Order Not Process Through Cron """.format(pick.id))
        return True
    
    def oneclick_done_sale_process(self):
        self.action_confirm()
        self.auto_process_delivery_order(self.picking_ids)
