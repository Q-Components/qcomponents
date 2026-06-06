from odoo import fields, models, api
from datetime import date
from dateutil.relativedelta import relativedelta

class SaleOrder(models.Model):
    _inherit = "sale.order"

    total_order_amount = fields.Monetary(string='Total Order Amount', compute='compute_total_order_amount',store=True,copy=False)
    has_unshipped_products = fields.Boolean(string="Has Unshipped Products",store=False,search='_search_unshipped',)

    @api.depends('amount_total')
    def compute_total_order_amount(self):
        for ord in self:
            ord.total_order_amount = ord.amount_total

    def action_create_payment(self):
        action = self.env.ref("advanced_sales_shipping_management_vts.action_create_payment_wizard")
        return action.read()[0]

    def _search_unshipped(self, operator, value):
        orders = self.env['sale.order'].search([
            ('state', 'in', ['sale', 'done']),
        ])
        unshipped_ids = []
        for order in orders:
            product_lines = order.order_line.filtered(
                lambda line: not line.is_delivery
                             and not line.display_type
                             and line.product_id.type == 'consu'
            )
            for line in product_lines:
                if line.product_uom_qty > line.qty_delivered:
                    unshipped_ids.append(order.id)
                    break

        return [('id', 'in', unshipped_ids)]


    @api.model
    def get_dashboard_data(self):
        today = date.today()
        currency = self.env.company.currency_id

        # Today
        today_orders = self.search([
            ('state', '=', 'sale'),
            ('date_order', '>=', f'{today} 00:00:00'),
            ('date_order', '<=', f'{today} 23:59:59'),
        ])

        # This Week
        week_start = today - relativedelta(days=today.weekday())
        week_end = week_start + relativedelta(days=6)
        weekly_orders = self.search([
            ('state', '=', 'sale'),
            ('date_order', '>=', f'{week_start} 00:00:00'),
            ('date_order', '<=', f'{week_end} 23:59:59'),
        ])

        # This Month
        month_start = today.replace(day=1)
        month_end = (month_start + relativedelta(months=1)) - relativedelta(days=1)
        monthly_orders = self.search([
            ('state', '=', 'sale'),
            ('date_order', '>=', f'{month_start} 00:00:00'),
            ('date_order', '<=', f'{month_end} 23:59:59'),
        ])

        # Pending Orders
        pending_count = self.search_count([
            ('state', 'in', ['draft', 'sent']),
        ])

        return {
            'today_sales': sum(today_orders.mapped('amount_total')),
            'weekly_sales': sum(weekly_orders.mapped('amount_total')),
            'monthly_sales': sum(monthly_orders.mapped('amount_total')),
            'pending_orders': pending_count,
            'pending_deliveries': self._get_pending_delivered(),
            'overdue_quotations': self._get_overdue_quotations(),
            'currency_symbol': currency.symbol or '$',
        }

    def _get_pending_delivered(self):
        domain = self._search_unshipped('=', True)
        return self.search_count(domain)

    def _get_overdue_quotations(self):
        return self.search_count([
            ('state', 'in', ['draft', 'sent']),
            ('validity_date', '<', date.today()),
            ('validity_date', '!=', False),
        ])


    @api.onchange("order_line")
    def apply_partner_discount(self):
        if not self.partner_id or not self.partner_id.sale_order_discount:
            return
        product_lines = self.order_line.filtered(
            lambda l: not l.display_type and not l.is_delivery and l.product_id.type == 'consu'
        )
        if not product_lines:
            return
        for line in product_lines:
            line.discount = self.partner_id.sale_order_discount * 100

    def action_today_sales(self):
        today = date.today()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Today Sales',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [
                ('state', '=', 'sale'),
                ('date_order', '>=', f'{today} 00:00:00'),
                ('date_order', '<=', f'{today} 23:59:59'),
            ],
        }

    def action_weekly_sales(self):
        today = date.today()
        week_start = today - relativedelta(days=today.weekday())
        week_end = week_start + relativedelta(days=6)

        return {
            'type': 'ir.actions.act_window',
            'name': 'Weekly Sales',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [
                ('state', '=', 'sale'),
                ('date_order', '>=', f'{week_start} 00:00:00'),
                ('date_order', '<=', f'{week_end} 23:59:59'),
            ],
        }

    def action_monthly_sales(self):
        today = date.today()
        month_start = today.replace(day=1)
        month_end = (month_start + relativedelta(months=1)) - relativedelta(days=1)

        return {
            'type': 'ir.actions.act_window',
            'name': 'Monthly Sales',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [
                ('state', '=', 'sale'),
                ('date_order', '>=', f'{month_start} 00:00:00'),
                ('date_order', '<=', f'{month_end} 23:59:59'),
            ],
        }

    def action_pending_orders(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Pending Orders',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [
                ('state', 'in', ['draft', 'sent']),
            ],
        }

    def action_pending_deliveries(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Pending Deliveries',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': self._search_unshipped('=', True),
        }

    def action_overdue_quotations(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Overdue Quotations',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [
                ('state', 'in', ['draft', 'sent']),
                ('validity_date', '<', date.today()),
                ('validity_date', '!=', False),
            ],
        }


