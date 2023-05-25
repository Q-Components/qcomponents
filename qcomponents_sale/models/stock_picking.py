from odoo import models, fields, api
from datetime import datetime


class StockPicking(models.Model):
    _inherit = "stock.picking"

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
                inv_id.with_user(1).action_post()
                self.with_user(1).generate_account_payment(inv_id)
        return res
