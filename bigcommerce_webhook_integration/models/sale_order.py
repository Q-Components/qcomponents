from odoo import fields, models, api,_
import logging

_logger = logging.getLogger("oneclick_done_sale")

class SaleOrder(models.Model):
    _inherit = "sale.order"
    
    def auto_process_delivery_order(self,picking_ids):
        for pick in picking_ids:
            is_valid = pick.prepare_picking_for_transfer()
            if is_valid:
                pick.with_user(1).action_done()
                pick.message_post(body=_("Delivery Order Process Through OneClickSaleOrder"))
                self._cr.commit()
            else:
                _logger.info("Need to Review Delivery Order Not Process Through Cron """.format(pick.id))
        return True
    
    def oneclick_done_sale_process(self):
        self.action_confirm()
        self.auto_process_delivery_order(self.picking_ids)
