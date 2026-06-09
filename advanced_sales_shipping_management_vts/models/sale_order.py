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
        today_sales_result = self._read_group(
            [
                ('state', '=', 'sale'),
                ('date_order', '>=', f'{today} 00:00:00'),
                ('date_order', '<=', f'{today} 23:59:59'),
            ],
            aggregates=['amount_total:sum'],
        )

        today_sales = today_sales_result[0][0] if today_sales_result else 0.0

        # This Week
        week_start = today - relativedelta(days=today.weekday())
        week_end = week_start + relativedelta(days=6)
        weekly_sales_result = self._read_group(
            [
                ('state', '=', 'sale'),
                ('date_order', '>=', f'{week_start} 00:00:00'),
                ('date_order', '<=', f'{week_end} 23:59:59'),
            ],
            aggregates=['amount_total:sum'],
        )

        weekly_sales = weekly_sales_result[0][0] if weekly_sales_result else 0.0

        # This Month
        month_start = today.replace(day=1)
        month_end = (month_start + relativedelta(months=1)) - relativedelta(days=1)
        monthly_sales_result = self._read_group(
            [
                ('state', '=', 'sale'),
                ('date_order', '>=', f'{month_start} 00:00:00'),
                ('date_order', '<=', f'{month_end} 23:59:59'),
            ],
            aggregates=['amount_total:sum'],
        )

        monthly_sales = monthly_sales_result[0][0] if monthly_sales_result else 0.0

        return {
            'today_sales': today_sales or 0.0,
            'weekly_sales': weekly_sales or 0.0,
            'monthly_sales': monthly_sales or 0.0,
            'pending_deliveries': self._get_pending_delivered(),
            'overdue_sale_orders': self._get_overdue_sale_orders(),
            "new_customer_this_month": self._get_new_customers_this_month(),
            'currency_symbol': currency.symbol or '$',
        }

    def _get_pending_delivered(self):
        days = int(self.env['ir.config_parameter'].sudo().get_param(
            'advanced_sales_shipping_management_vts.pending_delivery_days'
        ))
        from_date = date.today() - relativedelta(days=days)

        backorder_pickings = self.env['stock.picking'].search([
            ('sale_id', '!=', False),
            ('backorder_id', '!=', False),
            ('state', '!=', 'cancel'),
        ])
        sale_ids_with_backorder = backorder_pickings.mapped('sale_id').ids

        return self.search_count([
            ('date_order', '>=', from_date),
            ('id', 'in', sale_ids_with_backorder),
            ('id', 'in', self._search_unshipped('=', True)[0][2]),
        ])

    def _get_overdue_sale_orders(self):
        days = int(
            self.env["ir.config_parameter"].sudo().get_param(
                "advanced_sales_shipping_management_vts.overdue_sale_days",)
        )

        from_date = date.today() - relativedelta(days=days)

        overdue_invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('invoice_date_due', '<', date.today()),
            ('invoice_date', '>=', from_date),
        ])

        return self.search_count([
            ('state', '=', 'sale'),
            ('invoice_ids', 'in', overdue_invoices.ids),
        ])


    def _get_new_customers_this_month(self):
        today = date.today()

        month_start = today.replace(day=1)

        customer_ids = self.search([
            ('state', '=', 'sale'),
            ('partner_id.create_date', '>=', month_start),
        ]).mapped('partner_id').ids

        return len(set(customer_ids))

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

    def action_pending_deliveries(self):
        days = int(self.env['ir.config_parameter'].sudo().get_param(
            'advanced_sales_shipping_management_vts.pending_delivery_days'
        ))
        from_date = date.today() - relativedelta(days=days)

        backorder_pickings = self.env['stock.picking'].search([
            ('sale_id', '!=', False),
            ('backorder_id', '!=', False),
            ('state', '!=', 'cancel'),
        ])
        sale_ids_with_backorder = backorder_pickings.mapped('sale_id').ids

        domain = [
            ('date_order', '>=', from_date),
            ('id', 'in', sale_ids_with_backorder),
            ('id', 'in', self._search_unshipped('=', True)[0][2]),
        ]

        return {
            'type': 'ir.actions.act_window',
            'name': 'Pending Deliveries',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': domain,
        }

    def action_overdue_sale_orders(self):
        days = int(
            self.env["ir.config_parameter"].sudo().get_param(
                "advanced_sales_shipping_management_vts.overdue_sale_days")
        )

        from_date = date.today() - relativedelta(days=days)

        overdue_invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('invoice_date_due', '<', date.today()),
            ('invoice_date', '>=', from_date),
        ])

        overdue_order_ids = self.search([
            ('state', '=', 'sale'),
            ('invoice_ids', 'in', overdue_invoices.ids),
        ]).ids

        return {
            'type': 'ir.actions.act_window',
            'name': 'Overdue Sale Orders',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('id', 'in', overdue_order_ids)],
        }

    def action_new_customers_this_month(self):
        today = date.today()
        month_start = today.replace(day=1)


        return {
            'type': 'ir.actions.act_window',
            'name': 'New Customers This Month Sales Order',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
             'domain': [
            ('state', '=', 'sale'),
            ('partner_id.create_date', '>=', month_start),
        ],
        }


