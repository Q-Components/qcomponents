from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging
from datetime import datetime
_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"
    
    account_invoice_ids = fields.Many2many('account.move', string="Account Invoice", copy=False)

    def prepare_picking_for_transfer(self):
        self.ensure_one()
        if self.state == 'done':
            _logger.info("%s (Picking Status) : Could not process. Picking already in DONE state." %self.name)
            return False
        if self.state == 'draft':
            self.with_user(1).action_confirm()
            if self.state != 'assigned':
                self.with_user(1).action_assign()
                if self.state != 'assigned':
                    _logger.info("%s (Picking Status) : Could not reserve all requested products. Please use the \'Check Availability\' button to handle the reservation manually." %self.name)
                    return False
        if self.state == 'assigned' :
            for move in self.move_lines:
                if sum(move.move_line_ids.mapped('product_uom_qty')) >= move.sale_line_id.quantity_shipped and len(move.move_line_ids) == 1:
                    for move_line in move.move_line_ids:
                        move_line.product_uom_qty = move.sale_line_id.quantity_shipped
                        move_line.qty_done = move.sale_line_id.quantity_shipped
                elif sum(move.move_line_ids.mapped('product_uom_qty')) <= move.sale_line_id.quantity_shipped:
                    for move_line in move.move_line_ids:
                        move_line.qty_done = move_line.product_uom_qty
                else:
                    _logger.info("%s (Picking Status) : Could not transfer because there is a possibility of BackOrder. Please check delivery order." % self.name)
                    return False
                    
#             if self._check_backorder():
#                 _logger.info(
#                     "%s (Picking Status) : Could not transfer because there is a possibility of BackOrder. Please check delivery order." % self.name)
#                 for move in self.move_lines:
#                     for move_line in move.move_line_ids:
#                         move_line.product_uom_qty = move_line.qty_done
#                         move_line.qty_done = 0
#                 return False
        else :
            _logger.info("{} (Picking Status) : Could not process the picking because state is not as expected '{}'.".format(self.name, self.state))
            return False
        return True
    
    def prepare_supplier_invoice_data(self):
        self.ensure_one()
        return {
            'type': 'in_invoice',
            'ref': self.name,
            'partner_id': self.purchase_id.partner_id.id,
            'invoice_date': self.scheduled_date.date(),
            'invoice_origin': self.purchase_id.name,
            'currency_id': self.purchase_id.currency_id.id,
            'company_id': self.purchase_id.company_id.id
        }
    
    def prepare_invoice_line_data(self, line):
        self.ensure_one()
        prod_accounts = line.product_id.product_tmpl_id._get_product_accounts()
        return {
            'display_type': line.display_type,
            'sequence': line.sequence,
            'name': line.name,
            'product_id': line.product_id.id,
            'product_uom_id': line.product_uom.id,
            'quantity': line.product_qty,
            'price_unit': line.price_unit,
            'tax_ids': [(6,0,line.taxes_id.ids)],
            'account_id':prod_accounts['stock_input'].id,
            'purchase_line_id':line.id
        }
    
    def generate_account_payment(self,invoice_obj):
        if invoice_obj.type == 'out_invoice':
            payment_type = 'inbound'
            partner_type='customer'
        else:
            payment_type = 'outbound'
            partner_type='supplier'
        journal_id = self.env['account.journal'].sudo().search([('company_id','=',self.company_id.id),('type','=','bank')],limit=1)    
        payment_method_obj = self.env['account.payment.method'].search([('payment_type','=',payment_type),('code','=','manual')])
               
        vals = {
                'payment_type':payment_type ,
                'partner_type':partner_type,
                'journal_id' : journal_id.id,
                'amount' : invoice_obj.amount_total,
                'currency_id':invoice_obj.currency_id.id,
                'payment_method_id' : payment_method_obj.id,
                'payment_date':invoice_obj.invoice_date or datetime.now().today(),
                'communication':invoice_obj.name,
                'partner_id':invoice_obj.partner_id.id,
                'invoice_ids':[(6, 0, invoice_obj.ids)],
                'company_id':self.company_id.id
            }
        payment = self.env['account.payment'].new(vals)
        payment.with_user(1)._compute_payment_difference()
        payment.with_user(1)._onchange_payment_type()
        vals = payment.with_user(1)._convert_to_write(payment._cache)
        vals.update({'currency_id':invoice_obj.company_id.currency_id.id})
        payment_id = self.env['account.payment'].with_user(1).create(vals)
        payment_id.with_user(1).post()
    
    def action_done(self):
        result = super(StockPicking, self).action_done()
        for picking in self:
            if picking and picking.sale_id:
                for backorder in picking.backorder_ids: 
                    backorder.action_cancel()
                if picking.sale_id.company_id.auto_generate_invoice:
                    partner_location = self.env.ref('stock.stock_location_customers').id
                    if picking.location_dest_id.id == partner_location:
                        inv_id = picking.sale_id._create_invoices()
                        self.account_invoice_ids = [(4, inv_id.id)]
                        if picking.sale_id.company_id.invoice_generated_on == 'open':
                            inv_id.with_user(1).action_post()
                        if picking.sale_id.company_id.invoice_generated_on == 'paid':
                            inv_id.with_user(1).action_post()
                            self.with_user(1).generate_account_payment(inv_id)
        return result

    def action_view_account_invoice(self):
        if self.sale_id:
            invoices = self.mapped('account_invoice_ids')
            action = self.env.ref('account.action_move_out_invoice_type').read()[0]
            if len(invoices) > 1:
                action['domain'] = [('id', 'in', invoices.ids)]
            elif len(invoices) == 1:
                action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
                action['res_id'] = invoices.ids[0]
            else:
                action = {'type': 'ir.actions.act_window_close'}
            return action
        elif self.purchase_id:
            action = self.env.ref('account.action_move_in_invoice_type')
            result = action.read()[0]
            if self.purchase_id:
                result['context'] = {'type': 'in_invoice', 'default_purchase_id': self.purchase_id.id}
            if self.sale_id:
                result['context'] = {'type': 'out_invoice', 'default_sale_id': self.sale_id.id}

            if not self.account_invoice_ids:
                journal_domain = [
                    ('type', '=', 'purchase'),
                    ('company_id', '=', self.company_id.id),
                    ('currency_id', '=', self.purchase_id.currency_id.id),
                ]
                default_journal_id = self.env['account.journal'].search(journal_domain, limit=1)
                if default_journal_id:
                    result['context']['default_journal_id'] = default_journal_id.id
            else:
                # Use the same account journal than a previous invoice
                result['context']['default_journal_id'] = self.account_invoice_ids.journal_id.id

            if len(self.account_invoice_ids) != 1:
                result['domain'] = "[('id', 'in', " + str(self.account_invoice_ids) + ")]"
            elif len(self.account_invoice_ids) == 1:
                res = self.env.ref('account.view_move_form', False)
                result['views'] = [(res and res.id or False, 'form')]
                result['res_id'] = self.account_invoice_ids.id
            return result
    