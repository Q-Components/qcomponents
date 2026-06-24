from odoo import api, models, fields
from datetime import timedelta


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _percentage_change(self, current, previous):
        if not previous:
            return 100.0 if current > 0 else 0.0
        return round(((current - previous) / previous) * 100, 1)

    def _get_invoice_data(self, sale_orders):
        invoice_ids = sale_orders.mapped('invoice_ids').filtered(
            lambda inv: inv.move_type == 'out_invoice'
            and inv.state in ['posted', 'draft']
        )

        unpaid_invoice_ids = invoice_ids.filtered(
            lambda inv: inv.payment_state in ['not_paid', 'partial']
        )

        unpaid_amount = sum(
            unpaid_invoice_ids.mapped('amount_residual')
        )

        return {
            "invoice_ids": invoice_ids,
            "unpaid_invoice_ids": unpaid_invoice_ids,
            "total_invoices": len(invoice_ids),
            "unpaid_amount": round(unpaid_amount, 2),
        }

    def _get_delivery_counts(self, sale_orders):

        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)],
            limit=1
        )

        if not warehouse:
            return {
                'full': 0,
                'partial': 0,
                'pending': 0,
                'cancelled': 0,
            }

        if warehouse.delivery_steps == 'ship_only':
            return self._get_one_step_delivery_status(sale_orders)

        elif warehouse.delivery_steps == 'pick_ship':
            return self._get_two_step_delivery_status(sale_orders)

        return self._get_three_step_delivery_status(sale_orders)

    def _get_alerts_data(self, sale_orders):

        today = fields.Date.today()

        stock_shortage_orders = sale_orders.filtered(
            lambda so: any(
                line.product_id.is_storable
                and line.product_id.qty_available < line.product_uom_qty
                for line in so.order_line
            )
        )

        overdue_invoices = sale_orders.mapped('invoice_ids').filtered(
            lambda inv:
                inv.move_type == 'out_invoice'
                and inv.state == 'posted'
                and inv.payment_state in ['not_paid', 'partial']
                and inv.invoice_date_due
                and inv.invoice_date_due < today
        )

        pending_delivery_orders = self.env['sale.order']

        for order in sale_orders:

            if not order.date_order:
                continue

            if order.date_order.date() > (today - timedelta(days=7)):
                continue

            counts = self._get_delivery_counts(order)

            if counts['pending']:
                pending_delivery_orders |= order

        return {
            "stock_shortage": len(stock_shortage_orders),
            "invoice_overdue": len(overdue_invoices),
            "pending_delivery_7": len(pending_delivery_orders),

            "stock_shortage_order_ids": stock_shortage_orders.ids,
            "invoice_overdue_ids": overdue_invoices.ids,
            "pending_delivery_order_ids": pending_delivery_orders.ids,
        }

    def _get_returns_data(self, sale_orders):
        returns = self.env['stock.picking'].search([
            ('sale_id', 'in', sale_orders.ids),
            ('picking_type_id.code', '=', 'incoming'),
            ('move_ids.origin_returned_move_id', '!=', False),
        ])
        return {
            "return_ids": returns.ids,
            "total_returns": len(returns),
        }

    def _get_shipping_charges(self, sale_orders):
        shipping_lines = sale_orders.mapped('order_line').filtered(
            lambda l: l.is_delivery
        )
        return sum(shipping_lines.mapped('price_total'))

    def _get_carrier_shipping_chart(self, sale_orders):
        shipping_lines = sale_orders.mapped('order_line').filtered(lambda l: l.is_delivery)
        carrier_costs = {}

        for line in shipping_lines:
            carrier = line.order_id.carrier_id.name or "No Carrier"
            carrier_costs[carrier] = carrier_costs.get(carrier, 0) + line.price_total
        return [
            {"carrier": carrier, "cost": round(cost, 2)}
            for carrier, cost in sorted(
                carrier_costs.items(),
                key=lambda item: item[1],
                reverse=True
            )
        ]

    def _get_delivery_data(self, sale_orders):

        counts = self._get_delivery_counts(sale_orders)

        return {
            "delivery_ids": [],
            "delivery_pending": counts['pending'],
        }

    def _get_delivery_chart_data(self, sale_orders):

        counts = self._get_delivery_counts(sale_orders)

        return [
            {
                'status': 'Fully Delivered',
                'count': counts['full']
            },
            {
                'status': 'Partially Delivered',
                'count': counts['partial']
            },
            {
                'status': 'Pending Delivery',
                'count': counts['pending']
            },
            {
                'status': 'Cancelled',
                'count': counts['cancelled']
            }
        ]

    def _get_one_step_delivery_status(self, sale_orders):

        counts = {
            'full': 0,
            'partial': 0,
            'pending': 0,
            'cancelled': 0,
        }

        pending_states = [
            'draft',
            'waiting',
            'confirmed',
            'assigned'
        ]

        for order in sale_orders:

            outgoing = order.picking_ids.filtered(
                lambda p:
                    p.picking_type_code == 'outgoing'
            )
            if not outgoing:
                continue

            states = outgoing.mapped('state')
            if all(state == 'cancel' for state in states):
                counts['cancelled'] += 1

            elif (
                any(state == 'done' for state in states)
                and any(state in pending_states for state in states)
            ):
                counts['partial'] += 1

            elif all(state == 'done' for state in states):
                counts['full'] += 1

            else:
                counts['pending'] += 1

        return counts

    def _get_two_step_delivery_status(self, sale_orders):

        counts = {
            'full': 0,
            'partial': 0,
            'pending': 0,
            'cancelled': 0,
        }

        pending_states = ['draft', 'waiting', 'confirmed', 'assigned',]

        for order in sale_orders:

            pickings = order.picking_ids
            outgoing = pickings.filtered(lambda p: p.picking_type_code == 'outgoing')

            internal = pickings.filtered(lambda p: p.picking_type_code == 'internal')

            outgoing_states = outgoing.mapped('state')
            internal_states = internal.mapped('state')

            # ---------------------------------
            # Backorder logic
            # ---------------------------------

            done_outgoing = outgoing.filtered(lambda p: p.state == 'done')

            remaining_outgoing = outgoing.filtered(lambda p: p.state != 'done')

            # done + ready
            if done_outgoing:

                active_remaining = remaining_outgoing.filtered(lambda p: p.state != 'cancel')
                if active_remaining:
                    counts['partial'] += 1
                    continue

                # done + cancel
                counts['full'] += 1
                continue

            # ---------------------------------
            # Fully Delivered
            # ---------------------------------

            if outgoing and all(
                state == 'done'
                for state in outgoing_states
            ):
                counts['full'] += 1
                continue

            # ---------------------------------
            # Cancelled
            # ---------------------------------

            if outgoing and all(
                state == 'cancel'
                for state in outgoing_states
            ):
                counts['cancelled'] += 1
                continue

            if internal and all(
                state == 'cancel'
                for state in internal_states
            ):
                counts['cancelled'] += 1
                continue

            # ---------------------------------
            # Pending
            # ---------------------------------

            if (any(state in pending_states for state in internal_states)
                or any(state in pending_states for state in outgoing_states)):
                counts['pending'] += 1
                continue

            counts['pending'] += 1

        return counts

    def _get_three_step_delivery_status(self, sale_orders):

        counts = {'full': 0, 'partial': 0, 'pending': 0, 'cancelled': 0}

        pending_states = ['draft', 'waiting', 'confirmed', 'assigned']

        for order in sale_orders:

            pickings = order.picking_ids

            outgoing = pickings.filtered(lambda p: p.picking_type_code == 'outgoing')
            internal = pickings.filtered(lambda p: p.picking_type_code == 'internal')

            pick_operations = internal.filtered(lambda p: 'pick' in (p.picking_type_id.name or '').lower())
            pack_operations = internal.filtered(lambda p: 'pack' in (p.picking_type_id.name or '').lower())

            all_relevant = pick_operations | pack_operations | outgoing

            if not all_relevant:
                continue

            # ---------------------------------
            # 1. Cancelled: last existing stage in the chain is fully cancelled
            # ---------------------------------
            last_stage = outgoing or pack_operations or pick_operations

            if last_stage and all(p.state == 'cancel' for p in last_stage):
                counts['cancelled'] += 1
                continue

            active = all_relevant.filtered(lambda p: p.state != 'cancel')

            if not active:
                counts['cancelled'] += 1
                continue

            done = active.filtered(lambda p: p.state == 'done')
            not_done = active.filtered(lambda p: p.state != 'done')

            # ---------------------------------
            # 2. Fully Delivered
            # ---------------------------------
            if outgoing and all(p.state == 'done' for p in outgoing) and not pick_operations.filtered(lambda p: p.state in pending_states) and not pack_operations.filtered(lambda p: p.state in pending_states):
                counts['full'] += 1
                continue

            # ---------------------------------
            # 3. Partial: at least one outgoing done, but not all (backorder still open)
            # ---------------------------------
            outgoing_done = outgoing.filtered(lambda p: p.state == 'done')
            outgoing_not_done = outgoing.filtered(lambda p: p.state != 'done' and p.state != 'cancel')

            if outgoing_done and outgoing_not_done:
                counts['partial'] += 1
                continue

            if outgoing_done and not outgoing_not_done:
                # all created outgoing are done — but check if pick/pack still has open backorder
                if pick_operations.filtered(lambda p: p.state in pending_states) or pack_operations.filtered(lambda p: p.state in pending_states):
                    counts['partial'] += 1
                else:
                    counts['full'] += 1
                continue

            # ---------------------------------
            # 4. Pending: no outgoing done yet (still in pick/pack stage)
            # ---------------------------------
            if any(p.state in pending_states for p in active):
                counts['pending'] += 1
                continue

            counts['pending'] += 1

        return counts

    def _get_profit_data(self, sale_orders, total_sales):
        profit = 0.0

        for line in sale_orders.mapped('order_line'):
            cost = (
                line.product_id.standard_price
                * line.product_uom_qty
            )

            revenue = line.price_subtotal

            profit += (revenue - cost)
        gross_margin = (
            (profit / total_sales) * 100
            if total_sales else 0
        )

        return {
            "profit": round(profit, 2),
            "gross_margin": round(gross_margin, 2),
        }

    @api.model
    def get_dashboard_data(self, date_from=False, date_to=False):

        domain = []

        if date_from:
            domain.append(
                ('date_order', '>=', f"{date_from} 00:00:00")
            )

        if date_to:
            domain.append(
                ('date_order', '<=', f"{date_to} 23:59:59")
            )

        sale_domain = domain + [
            ('state', 'in', ['sale'])
        ]

        quotation_domain = domain + [
            ('state', 'in', ['draft', 'sent'])
        ]

        cancel_domain = domain + [
            ('state', '=', 'cancel')
        ]

        total_sale_orders = self.search_count(sale_domain)
        total_quotations = self.search_count(
            quotation_domain
        )
        cancelled_orders = self.search_count(
            cancel_domain
        )

        sales_data = self.read_group(
            sale_domain,
            ['amount_total:sum'],
            []
        )

        total_sales = (
            sales_data[0].get('amount_total', 0.0)
            if sales_data else 0.0
        )
        avg_order_value = (
            total_sales / total_sale_orders
            if total_sale_orders else 0.0
        )

        previous_sales = 0.0
        previous_orders = 0
        previous_quotations = 0
        previous_cancelled = 0

        previous_total_invoices = 0
        previous_unpaid_amount = 0
        previous_delivery_pending = 0
        previous_profit = 0
        previous_gross_margin = 0

        previous_returns = 0
        previous_shipping_charges = 0
        previous_avg_order_value = 0
        if date_from and date_to:

            current_from = fields.Date.to_date(
                date_from
            )

            previous_to = (
                current_from - timedelta(days=1)
            )

            previous_from = previous_to.replace(
                day=1
            )

            prev_base = [
                (
                    'date_order',
                    '>=',
                    f"{previous_from} 00:00:00"
                ),
                (
                    'date_order',
                    '<=',
                    f"{previous_to} 23:59:59"
                ),
            ]

            previous_sale_domain = prev_base + [
                ('state', 'in', ['sale'])
            ]

            previous_quotation_domain = prev_base + [
                ('state', 'in', ['draft', 'sent'])
            ]

            previous_cancel_domain = prev_base + [
                ('state', '=', 'cancel')
            ]

            previous_orders = self.search_count(previous_sale_domain)

            previous_quotations = self.search_count(previous_quotation_domain)

            previous_cancelled = self.search_count(previous_cancel_domain)

            prev_sales_data = self.read_group(
                previous_sale_domain,
                ['amount_total:sum'],
                []
            )

            previous_sales = (
                prev_sales_data[0].get(
                    'amount_total',
                    0.0
                )
                if prev_sales_data else 0.0
            )

            previous_sale_orders = self.search(
                previous_sale_domain
            )

            prev_invoice_data = (
                self._get_invoice_data(
                    previous_sale_orders
                )
            )

            prev_delivery_data = (
                self._get_delivery_data(
                    previous_sale_orders
                )
            )

            prev_profit_data = (
                self._get_profit_data(
                    previous_sale_orders,
                    previous_sales
                )
            )
            prev_returns_data = self._get_returns_data(previous_sale_orders)
            previous_total_invoices = (
                prev_invoice_data[
                    "total_invoices"
                ]
            )

            previous_unpaid_amount = (
                prev_invoice_data[
                    "unpaid_amount"
                ]
            )

            previous_delivery_pending = (
                prev_delivery_data[
                    "delivery_pending"
                ]
            )

            previous_profit = (
                prev_profit_data["profit"]
            )

            previous_gross_margin = (
                prev_profit_data[
                    "gross_margin"
                ]
            )
            

            previous_returns = prev_returns_data["total_returns"]
            previous_shipping_charges = self._get_shipping_charges(previous_sale_orders)
            previous_avg_order_value = (
                previous_sales / previous_orders
                if previous_orders else 0.0
            )
            
        sale_orders = self.search(sale_domain)
        returns_data = self._get_returns_data(sale_orders)
        total_returns = returns_data["total_returns"]
        total_shipping_charges = self._get_shipping_charges(sale_orders)
        alerts_data = self._get_alerts_data(sale_orders)
        invoice_data = self._get_invoice_data(
            sale_orders
        )

        delivery_data = self._get_delivery_data(
            sale_orders
        )

        profit_data = self._get_profit_data(
            sale_orders,
            total_sales
        )
        purchase_domain = [('date_approve', '>=', f"{date_from} 00:00:00"), ('date_approve', '<=', f"{date_to} 23:59:59"),('state','in',['purchase'])]
        purchase_orders = self.env['purchase.order'].search(purchase_domain)

        supplier_sales = {}

        for po in purchase_orders:
            supplier = po.partner_id.name or "Unknown Supplier"

            supplier_sales[supplier] = (
                supplier_sales.get(supplier, 0)
                + po.amount_total
            )

        top_suppliers_chart = [
            {
                "supplier": supplier,
                "amount": amount
            }
            for supplier, amount in sorted(
                supplier_sales.items(),
                key=lambda item: item[1],
                reverse=True
            )[:10]
        ]


        product_purchase = {}

        for line in purchase_orders.mapped('order_line'):
            product = line.product_id.name or "Unknown Product"

            product_purchase[product] = (
                product_purchase.get(product, 0.0)
                + line.product_qty
            )

        top_products_purchase_chart = [
            {
                "product": product,
                "qty": round(qty, 2),
            }
            for product, qty in sorted(
                product_purchase.items(),
                key=lambda item: item[1],
                reverse=True
            )[:10]
        ]

        monthly_sales = self.read_group(
            [('state', 'in', ['sale'])],
            ['amount_total:sum'],
            ['date_order:month'],
            orderby='date_order'
        )

        sales_chart_data = []

        for rec in monthly_sales:
            sales_chart_data.append({
                'month': rec['date_order:month'],
                'sales': rec['amount_total'],
            })

        company = self.env.company
        # Invoice Data for graph
        invoice_records = sale_orders.mapped('invoice_ids').filtered(
            lambda inv: inv.move_type == 'out_invoice'
            and inv.state in ['posted', 'draft']
        )

        paid_amount = sum(
            invoice_records.filtered(
                lambda inv: inv.payment_state == 'paid'
            ).mapped('amount_total')
        )

        partial_amount = sum(
            invoice_records.filtered(
                lambda inv: inv.payment_state == 'partial'
            ).mapped('amount_total')
        )

        unpaid_amount = sum(
            invoice_records.filtered(
                lambda inv: inv.payment_state == 'not_paid'
            ).mapped('amount_total')
        )

        overdue_amount = sum(
            invoice_records.filtered(
                lambda inv: inv.invoice_date_due
                and inv.invoice_date_due < fields.Date.today()
                and inv.payment_state in ['not_paid', 'partial']
            ).mapped('amount_residual')
        )

        invoice_total_amount = (
            paid_amount
            + partial_amount
            + unpaid_amount
        )
        product_sales = {}

        for line in sale_orders.mapped('order_line'):
            product = line.product_id.name

            product_sales[product] = (
                product_sales.get(product, 0)
                + line.price_subtotal
            )

        top_products_chart = [
            {"product": k, "sales": v}
            for k, v in sorted(
                product_sales.items(),
                key=lambda item: item[1],
                reverse=True
            )
        ]
        customer_sales = {}

        for order in sale_orders:
            customer = order.partner_id.name

            customer_sales[customer] = (
                customer_sales.get(customer, 0)
                + order.amount_total
            )

        top_customers_chart = [
            {
                "customer": customer,
                "sales": amount
            }
            for customer, amount in sorted(
                customer_sales.items(),
                key=lambda item: item[1],
                reverse=True
            )
        ]

        city_sales = {}

        for line in sale_orders.mapped('order_line'):

            city = (line.order_id.partner_id.city or "Unknown"
            )

            city_sales[city] = (
                city_sales.get(city, 0)
                + line.product_uom_qty
            )

        city_quantity_chart = [
            {
                "city": city,
                "qty": qty
            }
            for city, qty in sorted(
                city_sales.items(),
                key=lambda item: item[1],
                reverse=True
            )
        ]

        delivery_chart_data = self._get_delivery_chart_data(sale_orders)
        carrier_shipping_chart = self._get_carrier_shipping_chart(sale_orders)
       
        return {
            "currency": {
                "symbol": company.currency_id.symbol,
                "position": company.currency_id.position,
            },

            "filters": {
                "date_from": date_from,
                "date_to": date_to,
            },

            "kpis": {

                "total_sales":  round(total_sales, 2),

                "total_sales_change": self._percentage_change(
                                        total_sales,
                                        previous_sales
                                    ),

                "total_sale_orders": total_sale_orders,

                "total_sale_orders_change":
                    self._percentage_change(
                        total_sale_orders,
                        previous_orders
                    ),

                "total_quotations": total_quotations,

                "total_quotations_change":
                    self._percentage_change(
                        total_quotations,
                        previous_quotations
                    ),

                "avg_order_value": round(avg_order_value, 2),
                "avg_order_value_change":
                    self._percentage_change(
                        avg_order_value,
                        previous_avg_order_value
                    ),
                "cancelled_orders": cancelled_orders,

                "cancelled_orders_change":
                    self._percentage_change(
                        cancelled_orders,
                        previous_cancelled
                    ),

                "total_invoices": invoice_data[
                        "total_invoices"
                    ],

                "total_invoices_change":
                    self._percentage_change(
                        invoice_data[
                            "total_invoices"
                        ],
                        previous_total_invoices
                    ),

                "unpaid_amount": invoice_data[ "unpaid_amount"],

                "unpaid_amount_change":
                    self._percentage_change(
                        invoice_data[
                            "unpaid_amount"
                        ],
                        previous_unpaid_amount
                    ),

                "delivery_pending": delivery_data["delivery_pending"],
                "delivery_pending_change":
                    self._percentage_change(
                        delivery_data[
                            "delivery_pending"
                        ],
                        previous_delivery_pending
                    ),

                "profit": profit_data["profit"],

                "profit_change":
                    self._percentage_change(
                        profit_data["profit"],
                        previous_profit
                    ),

                "gross_margin":  profit_data["gross_margin"],
                "gross_margin_change":
                    round(
                        profit_data[
                            "gross_margin"
                        ] - previous_gross_margin,
                        2
                    ),
                "invoice_total_amount": round(
                    invoice_total_amount,
                    2
                ),
                "total_returns": total_returns,
                "total_returns_change": self._percentage_change(total_returns, previous_returns),
                "total_shipping_charges": round(total_shipping_charges, 2),
                "total_shipping_charges_change": self._percentage_change(total_shipping_charges, previous_shipping_charges),
            },
            "alerts": alerts_data,

            "records": {
                "invoice_ids": invoice_data["invoice_ids"].ids,

                "unpaid_invoice_ids":invoice_data[
                        "unpaid_invoice_ids"
                    ].ids,

                "delivery_ids": delivery_data[
                        "delivery_ids"
                    ],
                "return_ids": returns_data["return_ids"],
                "stock_shortage_order_ids":
                    alerts_data["stock_shortage_order_ids"],

                "invoice_overdue_ids":
                    alerts_data["invoice_overdue_ids"],

                "pending_delivery_order_ids":
                    alerts_data["pending_delivery_order_ids"],
            },

            "charts": {
                "monthly_sales":
                    sales_chart_data,
                "invoice_status": {
                    "paid": round(paid_amount, 2),
                    "partial": round(partial_amount, 2),
                    "unpaid": round(unpaid_amount, 2),
                    "overdue": round(overdue_amount, 2),
                },
                "top_products": top_products_chart,
                "top_customers": top_customers_chart,
                "city_quantity": city_quantity_chart,
               
                "delivery_status": delivery_chart_data,
                "carrier_shipping": carrier_shipping_chart,
                "top_suppliers": top_suppliers_chart,
                "top_purchased_products": top_products_purchase_chart,
            }
        }
