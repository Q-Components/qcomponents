from odoo import api, models
from datetime import date
from dateutil.relativedelta import relativedelta

class AccountMove(models.Model):
    _inherit = "account.move"


    @api.model
    def get_account_move_dashboard_data(self,move_type):

        today = date.today()
        currency = self.env.company.currency_id

        # Today
        today_moves = self.search([
            ('move_type', '=', move_type),
            ('state', '=', 'posted'),
            ('invoice_date', '=', today),
        ])

        # This Week
        week_start = today - relativedelta(days=today.weekday())
        week_end = week_start + relativedelta(days=6)
        weekly_moves = self.search([
            ('move_type', '=', move_type),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', week_start),
            ('invoice_date', '<=', week_end),
        ])

        # This Month
        month_start = today.replace(day=1)
        month_end = (month_start + relativedelta(months=1)) - relativedelta(days=1)
        monthly_moves = self.search([
            ('move_type', '=', move_type),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', month_start),
            ('invoice_date', '<=', month_end),
        ])

        partial_paid = self.search_count([
            ("payment_state", "=", "partial"),
            ('state', '=', 'posted'),
            ('move_type', '=', move_type),
        ])
        unpaid = self.search_count([
            ("payment_state", "=", "not_paid"),
            ('state', '=', 'posted'),
            ('move_type', '=', move_type),
        ])
        overdue = self.search_count([
            ('move_type', '=', move_type),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('invoice_date_due', '<', today),
        ])


        return {
            'today_amount': sum(today_moves.mapped('amount_total')),
            'weekly_amount': sum(weekly_moves.mapped('amount_total')),
            'monthly_amount': sum(monthly_moves.mapped('amount_total')),
            'partial_paid': partial_paid,
            'unpaid': unpaid,
            'overdue': overdue,
            'currency_symbol': currency.symbol or '$',
        }

    @api.model
    def action_today_amount(self,move_type):
        name = "Invoices" if move_type == 'out_invoice' else "Bills"
        today = date.today()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Today {name}',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'context': {'default_move_type': move_type},
            'domain': [
                ('move_type', '=', move_type),
                ('state', '=', 'posted'),
                ('invoice_date', '=', today),
            ],
        }

    @api.model
    def action_weekly_amount(self, move_type):
        name = "Invoices" if move_type == 'out_invoice' else "Bills"
        today = date.today()
        week_start = today - relativedelta(days=today.weekday())
        week_end = week_start + relativedelta(days=6)

        return {
            'type': 'ir.actions.act_window',
            'name': f'Weekly {name}',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'context': {'default_move_type': move_type},
            'domain': [
                ('move_type', '=', move_type),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', week_start),
                ('invoice_date', '<=', week_end),
            ],
        }

    @api.model
    def action_monthly_amount(self, move_type):
        name = "Invoices" if move_type == 'out_invoice' else "Bills"
        today = date.today()
        month_start = today.replace(day=1)
        month_end = (month_start + relativedelta(months=1)) - relativedelta(days=1)

        return {
            'type': 'ir.actions.act_window',
            'name': f'Monthly {name}',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'context': {'default_move_type': move_type},
            'domain': [
                ('move_type', '=', move_type),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', month_start),
                ('invoice_date', '<=', month_end),
            ],
        }
