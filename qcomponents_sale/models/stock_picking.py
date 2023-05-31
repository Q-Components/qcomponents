from odoo import models, fields, api
from datetime import datetime


class StockPicking(models.Model):
    _inherit = "stock.picking"

    account_invoice_ids = fields.Many2many('account.move', string="Account Invoice", copy=False)

    def generate_account_payment(self, invoice_obj):
        if invoice_obj.move_type == 'out_invoice':
            payment_type = 'inbound'
            partner_type = 'customer'
        else:
            payment_type = 'outbound'
            partner_type = 'supplier'
        journal_id = self.env['account.journal'].sudo().search(
            [('company_id', '=', self.company_id.id), ('type', '=', 'bank')], limit=1)
        vals = {
            'amount': invoice_obj.amount_total,
            'date': invoice_obj.invoice_date or datetime.now().today(),
            'ref': invoice_obj.name,
            'partner_id': invoice_obj.partner_id.id,
            'partner_type': partner_type,
            'currency_id': invoice_obj.currency_id.id,
            'journal_id': journal_id.id,
            'payment_type': payment_type
        }
        payment_id = self.env['account.payment'].with_user(1).create(vals)
        payment_id.with_user(1).action_post()
        # Payment reconcile process
        move_line_obj = self.env['account.move.line']
        domain = [('account_type', 'in', ('asset_receivable', 'liability_payable')), ('reconciled', '=', False)]
        line_ids = move_line_obj.search([('move_id', '=', invoice_obj.id)])
        to_reconcile = [line_ids.filtered(lambda line: line.account_type == 'asset_receivable')]

        for payment, lines in zip([payment_id], to_reconcile):
            payment_lines = payment.line_ids.filtered_domain(domain)
            for account in payment_lines.account_id:
                (payment_lines + lines).filtered_domain([('account_id', '=', account.id),
                                                         ('reconciled', '=', False)]).reconcile()

    def _action_done(self):
        res = super(StockPicking, self)._action_done()
        partner_location = self.env.ref('stock.stock_location_customers').id
        for picking in self:
            if picking.location_dest_id.id == partner_location:
                inv_id = picking.sale_id._create_invoices()
                self.account_invoice_ids = [(4, inv_id.id)]
                # inv_id.with_user(1).action_post()
                # self.with_user(1).generate_account_payment(inv_id)
        return res
        
    def action_view_account_invoice(self):
        if self.sale_id:
            invoices = self.mapped('account_invoice_ids')
            action = self.env.ref('account.action_move_out_invoice_type').sudo().read()[0]
            if len(invoices) > 1:
                action['domain'] = [('id', 'in', invoices.ids)]
            elif len(invoices) == 1:
                action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
                action['res_id'] = invoices.ids[0]
            else:
                action = {'type': 'ir.actions.act_window_close'}
            return action.sudo()
        elif self.purchase_id:
            action = self.env.ref('account.action_move_in_invoice_type')
            result = action.sudo().read()[0]
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
            return result.sudo()
