from .. import shopify
from odoo import models, fields, tools, _
from datetime import timedelta
from dateutil import parser
from ..shopify.pyactiveresource.connection import ClientError
from ..shopify.pyactiveresource.util import xml_to_dict
import urllib.parse as urlparse
import pytz
import re
import logging
import time

utc = pytz.utc

_logger = logging.getLogger("Shopify Order Queue")


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    instance_id = fields.Many2one('shopify.instance.integration', string="Instance", copy=False)
    shopify_order_reference_id = fields.Char(string="Shopify Order Identification", copy=False,
                                             help="This is the represent the reference of shopify order")
    shopify_order_number = fields.Char(string="Shopify Order Number", copy=False,
                                       help="This is the represent the number of shopify order")
    financial_status = fields.Char(string="Financial Status", copy=False)
    fulfillment_status = fields.Char(string="Fulfillment Status", copy=False)
    sale_auto_workflow_id = fields.Many2one("order.workflow.automation", string="Sale Auto Workflow",
                                            copy=False)
    risk_ids = fields.One2many("shopify.risk.order", 'odoo_order_id', "Risks", copy=False)
    is_order_risky = fields.Boolean(string="Is Order Risky?", default=False, copy=False)
    shopify_order_closed_at = fields.Datetime(string='Order Closed At')

    def create_shopify_order_queue_job(self, instance_id, shopify_order_list):
        res_id_list = []
        batch_size = 50
        for shopify_orders in tools.split_every(batch_size, shopify_order_list):
            queue_id = self.env['order.data.queue'].generate_shopify_order_queue(instance_id)
            for order in shopify_orders:
                shopify_order_dict = order.to_dict()
                name = shopify_order_dict.get('name', '') or ''
                self.env['order.data.queue.line'].create_shopify_order_queue_line(shopify_order_dict.get('id'), 'draft',
                                                                                  name, shopify_order_dict, instance_id,
                                                                                  queue_id)
            res_id_list.append(queue_id.id)
        return res_id_list

    def import_orders_from_shopify_to_odoo(self, instance, from_date=False, to_date=False, shopify_order_ids=False):
        instance.test_shopify_connection()
        last_synced_date = fields.Datetime.now()
        res_id_list = False
        if shopify_order_ids:
            shopify_order_ls = self.fetch_orders_from_shopify_to_odoo(shopify_order_id=shopify_order_ids)
        if not from_date:
            from_date = fields.Datetime.now() - timedelta(10)
        if not to_date:
            to_date = fields.Datetime.now()
        if not shopify_order_ids:
            shopify_order_ls = self.fetch_orders_from_shopify_to_odoo(from_date=from_date, to_date=to_date)
        if shopify_order_ls:
            res_id_list = self.create_shopify_order_queue_job(instance, shopify_order_ls)
        if shopify_order_ids and res_id_list:
            self.env['order.data.queue'].browse(res_id_list).process_shopify_order_queue()
        if res_id_list:
            instance.last_order_synced_date = last_synced_date
            return res_id_list

    def fetch_orders_from_shopify_to_odoo(self, from_date=False, to_date=False, shopify_order_id=False):
        shopify_order_list, page_info = [], False
        if shopify_order_id:
            shopify_order_id = list(set(re.findall(re.compile(r"(\d+)"), shopify_order_id)))
            try:
                shopify_order_list = shopify.Order().find(status="open", ids=",".join(shopify_order_id))
                _logger.info(shopify_order_list)
            except Exception as error:
                _logger.info("Getting Some Error In Fetch The Order :: \n {}".format(error))
            return shopify_order_list

        if not shopify_order_id:
            while 1:
                if page_info:
                    page_wise_order_list = shopify.Order().find(page_info=page_info, limit=250)
                else:
                    page_wise_order_list = (
                        shopify.Order().find(status='open', fulfillment_status='unshipped', processed_at_min=from_date,
                                             processed_at_max=to_date, limit=250))
                page_url = page_wise_order_list.next_page_url
                parsed = urlparse.parse_qs(page_url)
                page_info = parsed.get('page_info', False) and parsed.get('page_info', False)[0] or False
                shopify_order_list += page_wise_order_list
                if not page_info:
                    break
        return shopify_order_list

    def auto_confirm_sale_order(self, instance_id, sale_order_id=False, log_id=False, line=False):
        """This method used for confirm sale order automatically if permission was granted in sale auto workflow for
        confirm sale order
        @param : instance_id : object of instance
                sale_order_id :object of created sale order
                log_id : object of main log
                line : object of log line
        """
        try:
            date_order = sale_order_id.date_order
            sale_order_id.action_confirm()
            sale_order_id.date_order = date_order
            return True
        except Exception as e:
            line.state = 'failed'
            error_msg = 'Can not confirm sale order {0}'.format(
                sale_order_id.name)
            self.env['shopify.log.line'].generate_shopify_process_line('order', 'import', instance_id, error_msg,
                                                                       False, e, log_id, True)
            return False

    def auto_validate_delivery_order(self, instance_id, sale_order_id=False, log_id=False, line=False):
        """This method was used for validate delivery order based on sale auto work flow permission
         @param : instance_id : object of instance
                sale_order_id :object of created sale order
                log_id : object of main log
                line : object of log line
        """
        try:
            for picking_id in sale_order_id.picking_ids:
                for move_id in picking_id.move_ids_without_package:
                    if move_id.state in ['assigned']:
                        move_id.sudo().write({
                            'quantity_done': move_id.forecast_availability,
                        })
                # using below code we will validate delivery order automatically
                picking_id.with_context(skip_sms=True).button_validate()
                return True
        except Exception as e:
            line.state = 'partially_completed'
            error_msg = 'Can not validate delivery order of sale order - {0}'.format(
                sale_order_id.name)
            self.env['shopify.log.line'].generate_shopify_process_line('order', 'import', instance_id, error_msg,
                                                                       False, e, log_id, True)
            return False

    def create_invoice_payment(self, inv_id, journal_id, payment_method_line, amount, payment_date):
        """This method was used for create payment of invoice
            @param : inv_id : object of created invoice
                     journal_id : object of journal
                     payment_method_line : object of payment method
                     amount : amount of specific payment
                     payment_date : payment date
        """
        pmt_wizard = self.env['account.payment.register'].with_context(
            active_model='account.move',
            active_ids=inv_id.ids).create(
            {'payment_date': payment_date,
             'journal_id': journal_id.id,
             'payment_method_line_id': payment_method_line.id,
             'currency_id': inv_id.currency_id and inv_id.currency_id.id,
             'amount': amount,
             'group_payment': True,
             'communication': inv_id.name or inv_id.display_name or ' '})
        pmt_wizard._create_payments()

    def auto_create_and_validate_invoice(self, instance_id, sale_order_id=False, shopify_order_dict=False, log_id=False,
                                         line=False):
        """This method was used for creating and validate invoice and create payment (multiple payment if find in response)
            @param : instance_id : object of instance
                     sale_order_id : object of created sale order
                     shopify_order_dict : json response of shopify sale order
                     log_id : object of main log
                     line :  object of log line
        """

        try:
            if sale_order_id.shopify_order_reference_id and sale_order_id.financial_status in ['paid', 'Paid',
                                                                                               'PAID']:
                inv_wiz_id = self.env['sale.advance.payment.inv'].create(
                    {'sale_order_ids': [(6, 0, [sale_order_id.id])], 'advance_payment_method': 'delivered'})
                if inv_wiz_id:
                    inv_id = inv_wiz_id._create_invoices(sale_orders=sale_order_id)
                    inv_id.action_post()
                    # Below code will use for generate payment when invoice will be created
                    shopify_payment_gateway_names = shopify_order_dict.get('payment_gateway_names')
                    financial_status = self.env['shopify.financial.status.configuration'].search(
                        [('payment_gateway_id.name', '=', shopify_payment_gateway_names)], limit=1)
                    sale_auto_workflow_id = financial_status.sale_auto_workflow_id
                    journal_id = sale_auto_workflow_id.journal_id
                    payment_method_line = journal_id and journal_id.inbound_payment_method_line_ids.filtered(
                        lambda x: x.name.lower() == 'manual')
                    instance_id.test_shopify_connection()
                    try:
                        shopify_payment_transactions = shopify.Transaction.find(order_id=shopify_order_dict.get('id'))
                    except Exception as error:
                        _logger.info(error)
                        line.state = 'partially_completed'
                        error_msg = 'Can not find any transaction in order  - {0}'.format(
                            sale_order_id.name)
                        self.env['shopify.log.line'].generate_shopify_process_line('order', 'import', instance_id,
                                                                                   error_msg,
                                                                                   False, error, log_id, True)
                        return False
                    filtered_transactions = [transaction.to_dict() for transaction in shopify_payment_transactions if
                                             transaction and transaction.status == 'success' and transaction.kind in [
                                                 'capture', 'sale']]
                    for transaction in filtered_transactions:
                        amount = float(transaction.get('amount', 0.0)) if transaction and isinstance(transaction,
                                                                                                     dict) and transaction.get(
                            'amount', 0.0) else 0.0
                        payment_date = self.convert_order_date(transaction)
                        if payment_method_line:
                            self.create_invoice_payment(inv_id, journal_id, payment_method_line, amount, payment_date)

                    return True
        except Exception as e:
            line.state = 'partially_completed'
            error_msg = 'Can not validate and create invoice of sale order - {0}'.format(
                sale_order_id.name)
            self.env['shopify.log.line'].generate_shopify_process_line('order', 'import', instance_id, error_msg,
                                                                       False, e, log_id, True)
            return False

    def check_automatic_workflow_process_for_order(self, instance_id, shopify_order_dict, sale_order_id, log_id=False,
                                                   line=False):
        """This method was used for check automatic workflow for proceed the sale order automatically
            @param : instance_id : object of instance
                    shopify_order_dict : json response of shopify sale order
                    sale_order_id : object of sale order
                    log_id : object of log_id for creating log_line
                    line : object of specific order queue line

        """
        shopify_gateway_name = shopify_order_dict.get('gateway') or "no_payment_gateway"
        if not shopify_order_dict.get('gateway') and shopify_order_dict.get('payment_gateway_names'):
            shopify_gateway_name = shopify_order_dict.get('payment_gateway_names')[0]
        if shopify_gateway_name:
            financial_status = self.env['shopify.financial.status.configuration'].search(
                [('payment_gateway_id.name', '=', shopify_gateway_name)], limit=1)
            sale_auto_workflow_id = financial_status and financial_status.sale_auto_workflow_id or False
            if not sale_auto_workflow_id:
                # create log line
                return True

            result = False
            # Below code will use for confirm the sale order if confirm sale order boolean field was true in sale auto workflow
            if sale_auto_workflow_id and sale_auto_workflow_id.confirm_sale_order:
                vals = {'sale_auto_workflow_id': sale_auto_workflow_id.id}
                if sale_auto_workflow_id.policy_of_picking:
                    vals.update({'picking_policy': sale_auto_workflow_id.policy_of_picking})
                sale_order_id.write(vals)
                sale_order_id.sale_auto_workflow_id = sale_auto_workflow_id.id
                result = self.auto_confirm_sale_order(instance_id, sale_order_id, log_id, line)

            # Below code will use for confirm the delivery order if confirm delivery order boolean field was true in sale auto workflow
            if (
                    sale_auto_workflow_id and sale_auto_workflow_id.confirm_sale_order and sale_auto_workflow_id.validate_delivery_order and
                    sale_order_id.state == 'sale'):
                result = self.auto_validate_delivery_order(instance_id, sale_order_id, log_id, line)

            # Below code will use for create anf validate invoice if confirm sale order and create and validate invoice boolean field was true in sale auto workflow
            if sale_auto_workflow_id and sale_auto_workflow_id.confirm_sale_order and sale_auto_workflow_id.create_invoice and sale_order_id.state == 'sale':
                result = self.auto_create_and_validate_invoice(instance_id, sale_order_id, shopify_order_dict, log_id,
                                                               line)

            if sale_order_id and not sale_auto_workflow_id.confirm_sale_order and \
                    not sale_auto_workflow_id.validate_delivery_order and not sale_auto_workflow_id.create_invoice:
                return True

            return result

    def convert_order_date(self, order_response):
        if order_response.get("created_at", False):
            order_date = order_response.get("created_at", False)
            date_order = parser.parse(order_date).astimezone(utc).strftime("%Y-%m-%d %H:%M:%S")
        else:
            date_order = time.strftime("%Y-%m-%d %H:%M:%S")
            date_order = str(date_order)

        return date_order

    def get_order_currency(self, shopify_order_dictionary):
        currency_name = shopify_order_dictionary.get('currency')

        order_currency_id = self.env['res.currency'].search([('name', '=', currency_name)], limit=1)
        return order_currency_id

    def get_price_list(self, currency_id, instance_id):
        price_list_object = self.env['product.pricelist']
        price_list_id = instance_id.price_list_id or False
        if not price_list_id:
            price_list_id = price_list_object.search([('currency_id', '=', currency_id.id)], limit=1)
        return price_list_id

    def find_create_customer_in_odoo(self, instance_id, shopify_order_dict, log_id=False, line=False):
        """
        This method was used for search or create customer in odoo if we have not found customer in odoo then
        we call the api and create that customer in odoo
        @param : instance_id : object of instance
                 shopify_order_dict : json response of shopify sale order response
        @return : if not found customer id in response then return false otherwise return customer id
        """
        instance_id.test_shopify_connection()
        shopify_customer_id = shopify_order_dict.get('customer') and shopify_order_dict.get('customer').get('id')
        if not shopify_customer_id:
            return False
        odoo_customer_id = self.env['res.partner'].search([('shopify_customer_id', '=', shopify_customer_id)])
        if odoo_customer_id:
            return odoo_customer_id
        else:
            try:
                shopify_customer_data = shopify.Customer().find(shopify_customer_id)
            except Exception as e:
                _logger.info(e)
            so_customer_data = shopify_customer_data.to_dict()
            customer_id = self.env['res.partner'].create_update_customer_shopify_to_odoo(instance_id=instance_id,
                                                                                         so_customer_data=so_customer_data,
                                                                                         log_id=log_id)
            return customer_id

    def check_missing_value_details(self, lines, instance_id, line, order_number, log_id):
        """This method used to check the missing details in the order lines.
            @param lines : response of shopify sale order lines
                   instance_id :  object of instance
                   line : object of specific order queue line
                   order_number : shopify order number
                   log_id : object of created main log for create log line
            @return : mismatch : if found mismatch value then return true otherwise return false
        """
        mismatch = False

        for order_line in lines:
            shopify_product = self.search_listing_item(order_line, instance_id)
            if shopify_product:
                continue
            if order_line.get('gift_card', False):
                product = instance_id.shopify_gift_product_id or False
                if product:
                    continue
                error_msg = ("Please check instance may be order have gift card product \n"
                             "and in instance gift card product was not set so please upgrade the module because \n"
                             "we will set the some default product at instance level") % order_number

                line.write({'state': 'failed'})
                self.env['shopify.log.line'].generate_shopify_process_line('order', 'import', instance_id, error_msg,
                                                                           False, error_msg, log_id, True)
                continue
            if not shopify_product:
                variant_id = order_line.get("variant_id", False)
                product_id = order_line.get("product_id", False)
                if variant_id and product_id:
                    self.env['shopify.product.listing'].shopify_create_products(False, instance_id, log_id, product_id)
                    shopify_product_id = self.search_listing_item(order_line, instance_id)
                    if not shopify_product_id:
                        error_msg = "Product {0} {1} not found for Order {2}".format(
                            order_line.get("sku"), order_line.get("name"), order_number)
                        self.env['shopify.log.line'].generate_shopify_process_line('order', 'import', instance_id,
                                                                                   error_msg,
                                                                                   False, error_msg, log_id, True)
                        mismatch = True
                        break
        return mismatch

    def check_order_cancelled_or_refunded(self, existing_sale_order_id, shopify_order_dict):
        if existing_sale_order_id and existing_sale_order_id.invoice_ids:
            credit_note_wizard = self.env['account.move.reversal'].with_context(
                {'active_ids': [existing_sale_order_id.invoice_ids.id], 'active_id': existing_sale_order_id.invoice_ids.id, 'active_model': 'account.move'}).create(
                {
                    'refund_method': 'refund',
                    # this is the only mode for which the SO line is linked to the refund (https://github.com/odoo/odoo/commit/e680f29560ac20133c7af0c6364c6ef494662eac)
                    'reason': 'reason test create',
                    'journal_id': existing_sale_order_id.invoice_ids.journal_id.id,
                })
            credit_note = credit_note_wizard.reverse_moves()
            credit_note.action_post()
            return True

    def process_import_order_from_shopify(self, shopify_order_dict, instance_id, log_id=False, line=False):
        """This method was used for import the order from shopify to doo and process that order
            @param : shopify_order_dict : json response of specific order queue line
                     instance_id : object of instance__id
                     log_id : object of created log_id when process was start
                     line : object of specific order queue line
            return : sale order :- Object of sale order which is created in odoo based on order queue line response data
        """
        existing_sale_order_id = self.search(
            [('instance_id', '=', instance_id.id), ('shopify_order_reference_id', '=', shopify_order_dict.get('id')),
             ('shopify_order_number', '=', shopify_order_dict.get('name', ''))])
        if shopify_order_dict.get('cancelled_at'):
            if existing_sale_order_id:
                refund = self.check_order_cancelled_or_refunded(existing_sale_order_id, shopify_order_dict)
                print(refund)
                return True

        shopify_gateway_name = shopify_order_dict.get('gateway') or "no_payment_gateway"
        if not shopify_order_dict.get('gateway') and shopify_order_dict.get('payment_gateway_names'):
            shopify_gateway_name = shopify_order_dict.get('payment_gateway_names')[0]
        if shopify_gateway_name:
            financial_status = self.env['shopify.financial.status.configuration'].search(
                [('payment_gateway_id.name', '=', shopify_gateway_name)], limit=1)
            sale_auto_workflow_id = financial_status and financial_status.sale_auto_workflow_id or False
            if not sale_auto_workflow_id:
                return False
        customer_id = self.find_create_customer_in_odoo(instance_id, shopify_order_dict, log_id=False, line=False)
        if not customer_id:
            line.state = 'failed'
            error_msg = 'Can not find customer details in sale order response {0}'.format(
                shopify_order_dict.get('name', ''))
            self.env['shopify.log.line'].generate_shopify_process_line('order', 'import', instance_id, error_msg,
                                                                       False, error_msg, log_id, True)
            _logger.info("Customer details not found in response")
            return False
            # add logline
        date_order = self.convert_order_date(shopify_order_dict)
        currency_id = self.get_order_currency(shopify_order_dict)
        price_list_id = self.get_price_list(currency_id, instance_id)

        if existing_sale_order_id:
            line.sale_order_id = existing_sale_order_id.id
            msg = "Order Number {0} - {1}".format(existing_sale_order_id.name, "Is Already Exist In Odoo")
            line.state = 'completed'
            self.env['shopify.log.line'].generate_shopify_process_line('order', 'import', instance_id,
                                                                       msg,
                                                                       False, shopify_order_dict, log_id,
                                                                       False)
            return existing_sale_order_id
        lines = shopify_order_dict.get("line_items")
        order_number = shopify_order_dict.get("order_number")
        if self.check_missing_value_details(lines, instance_id, line, order_number, log_id):
            line.state = "failed"
            return False
        sale_order_id = self.create({"partner_id": customer_id and customer_id.id,
                                     "date_order": date_order,
                                     'company_id': instance_id.company_id.id or '',
                                     'warehouse_id': instance_id.warehouse_id.id or '',
                                     'state': 'draft',
                                     'pricelist_id': price_list_id and price_list_id.id or '',
                                     'name': shopify_order_dict.get('name', '')
                                     })
        line.sale_order_id = sale_order_id.id  # this line used for set the sale order id in order queue line sale order field
        if sale_order_id:
            order_lines = sale_order_id.create_sale_order_line(sale_order_id, shopify_order_dict,
                                                               instance_id=instance_id,
                                                               log_id=log_id, order_queue_line=line)
            if not order_lines:
                return False
            sale_order_id.write({'instance_id': instance_id.id,
                                 'shopify_order_reference_id': shopify_order_dict.get('id'),
                                 'shopify_order_number': shopify_order_dict.get('name', ''),
                                 'financial_status': shopify_order_dict.get('financial_status') or '',
                                 'fulfillment_status': shopify_order_dict.get('fulfillment_status') or ''})
            sale_order_id.generate_shopify_shipping_lines(sale_order_id, shopify_order_dict, instance_id=instance_id)
            risk_order_obj = self.env["shopify.risk.order"]
            instance_id.test_shopify_connection()
            risk_result = shopify.OrderRisk().find(order_id=str(shopify_order_dict.get('id')))
            if risk_result:
                risk_order_obj.shopify_create_risk_in_sale_order(risk_result, sale_order_id)
                risk = sale_order_id.risk_ids.filtered(lambda x: x.recommendation != "accept")
                if risk:
                    sale_order_id.is_order_risky = True

            check_process_status = self.check_automatic_workflow_process_for_order(instance_id, shopify_order_dict,
                                                                                   sale_order_id, log_id, line)
            if check_process_status:
                msg = "Sale Order {0} - {1}".format(sale_order_id.name, "Created Successfully")
                line.state = 'completed'
                self.env['shopify.log.line'].generate_shopify_process_line('order', 'import', instance_id,
                                                                           msg,
                                                                           False, shopify_order_dict, log_id,
                                                                           False)
                self._cr.commit()
                return sale_order_id

    def shopify_get_tax_id(self, instance, tax_lines, tax_included):
        """This method was used for find tax in odoo if not found then create new tax based on shopify_tax_line_response"""

        tax_id = []
        taxes = []
        company = instance.warehouse_id.company_id
        for tax in tax_lines:
            tax_rate = float(tax.get("rate", 0.0))
            tax_price = float(tax.get('price', 0.0))
            tax_title = tax.get("title")
            tax_rate = tax_rate * 100
            if tax_rate != 0.0 and tax_price != 0.0:
                if tax_included:
                    name = "%s_(%s %s included)_%s" % (tax_title, str(tax_rate), "%", company.name)
                else:
                    name = "%s_(%s %s excluded)_%s" % (tax_title, str(tax_rate), "%", company.name)
                tax_id = self.env["account.tax"].search([("price_include", "=", tax_included),
                                                         ("type_tax_use", "=", "sale"), ("amount", "=", tax_rate),
                                                         ("name", "=", name), ("company_id", "=", company.id)], limit=1)
                if not tax_id:
                    account_tax_object = self.env["account.tax"]

                    tax_id = account_tax_object.create({"name": name, "amount": float(tax_rate),
                                                        "type_tax_use": "sale", "price_include": tax_included,
                                                        "company_id": company.id})

                if tax_id:
                    taxes.append(tax_id.id)
        if taxes:
            tax_id = [(6, 0, taxes)]
        return tax_id

    def shopify_add_tax_in_sale_order_line(self, instance, line, order_response,
                                           line_vals, is_shipping=False, is_discount=False, previous_line=False):
        """ This method is used to set tax in the sale order line base on tax configuration in the
            Shopify setting in Odoo.
        """
        if instance.apply_tax_in_order == "create_shopify_tax":
            taxes_included = order_response.get("taxes_included") or False
            tax_ids = []
            if line and line.get("tax_lines"):
                if line.get("taxable"):
                    # This is used for when the one product is taxable and another product is not
                    # taxable
                    tax_ids = self.shopify_get_tax_id(instance,
                                                      line.get("tax_lines"),
                                                      taxes_included)

                if is_shipping:
                    # In the Shopify store there is configuration regarding tax is applicable on shipping or not,
                    # if applicable then this use.
                    tax_ids = self.shopify_get_tax_id(instance,
                                                      line.get("tax_lines"),
                                                      taxes_included)
            elif not line and previous_line:
                # Before modification, connector set order taxes on discount line but as per connector design,
                # we are creating discount line base on sale order line so it should apply sale order line taxes
                # in discount line not order taxes. It creates a problem while the customer is using multi taxes
                # in sale orders. so set the previous line taxes on the discount line.
                tax_ids = [(6, 0, previous_line.tax_id.ids)]
            line_vals["tax_id"] = tax_ids
            # When the one order with two products one product with tax and another product
            # without tax and apply the discount on order that time not apply tax on discount
            # which is
            if is_discount and not previous_line.tax_id:
                line_vals["tax_id"] = []
        return line_vals

    def crate_vals_for_sale_order_line(self, instance_id, quantity, price, product_id, sale_order_id,
                                       is_delivery=False):
        """
        This method used for prepare basic vals fo create sale order line in odoo
        @param : quantity :order line quantity,
                 price : price of sale order line
                 product_id : product detail of sale order line
                 sale_order_id : object of created sale order
                 is_delivery : boolean object of product is delivery or not
        @return : vals for creating order line
        """
        vals = {
            'order_id': sale_order_id.id,
            'product_id': product_id.id,
            'product_uom_qty': quantity,
            'price_unit': price,
            'is_delivery': is_delivery
        }
        return vals

    def search_listing_item(self, line, instance_id):
        """This method was used for find the product in odoo
            @param : line : dictionary of specific shopify sale order line
                    instance_id : object of instance
        """
        product_variant_id = line.get('variant_id')
        shopify_product_listing_item_id = self.env['shopify.product.listing.item'].search(
            [('shopify_product_variant_id', '=', product_variant_id), ('shopify_instance_id', '=', instance_id.id)])
        if not shopify_product_listing_item_id and line.get('sku'):
            shopify_product_listing_item_id = self.env['shopify.product.listing.item'].search(
                [('product_sku', '=', line.get('sku')), ('shopify_instance_id', '=', instance_id.id)])
            if shopify_product_listing_item_id:
                shopify_product_listing_item_id.shopify_product_variant_id = product_variant_id
            return False
        return shopify_product_listing_item_id

    def create_sale_order_line(self, sale_order_id, shopify_order_dict, instance_id=False, log_id=False,
                               order_queue_line=False):
        """This method was used for create a sale order line in odoo
            @param : sale_order_id : object of created sale order in parent method
                     shopify_order_dict : json response of shopify sale order
                     instance_id : object of instance
        """
        product_id = self.env['product.product']
        order_lines = shopify_order_dict.get('line_items')
        total_discount = shopify_order_dict.get("total_discounts", 0.0)
        previous_line = False
        if isinstance(order_lines, dict):
            order_lines = [order_lines]
        for line in order_lines:
            is_gift_card_line = False
            if line.get('gift_card'):
                product_id = instance_id.shopify_gift_product_id
                is_gift_card_line = True
            if not is_gift_card_line:
                shopify_product_id = self.env['shopify.product.listing.item'].search(
                    [('shopify_product_variant_id', '=', line.get('variant_id')),
                     ('shopify_instance_id', '=', instance_id.id)])
                product_id = shopify_product_id.product_id
            order_line = self.crate_vals_for_sale_order_line(instance_id, line.get('quantity'),
                                                             line.get('price'), product_id, sale_order_id)
            order_line.update({'shopify_order_line_id': line.get('id')})
            if is_gift_card_line:
                line_vals = {'is_gift_card_line': True}
                if line.get('name'):
                    line_vals.update({'name': line.get('name')})
                order_line.update(line_vals)

            order_line_vals = self.shopify_add_tax_in_sale_order_line(instance_id, line, shopify_order_dict, order_line)

            sale_order_line = self.env['sale.order.line'].create(order_line_vals)
            sale_order_line.with_context(round=False)._compute_amount()
            previous_line = sale_order_line

            # below code is check for add the discount line at sale order line
            if float(total_discount) > 0.0:
                discount_amount = 0.0
                for discount_allocation in line.get("discount_allocations"):
                    discount_amount += float(discount_allocation.get("amount"))
                if discount_amount > 0.0:
                    line_vals = self.crate_vals_for_sale_order_line(instance_id, 1,
                                                                    discount_amount * -1,
                                                                    instance_id.shopify_discount_product_id,
                                                                    sale_order_id)
                    order_line_vals = self.shopify_add_tax_in_sale_order_line(instance_id, order_line,
                                                                              shopify_order_dict,
                                                                              is_discount=False,
                                                                              previous_line=previous_line,
                                                                              line_vals=line_vals)

                    if instance_id.apply_tax_in_order == "odoo_tax" and previous_line:
                        order_line_vals["tax_id"] = previous_line.tax_id
                    order_line_vals.update({'name': "Discount for {0}".format(product_id.name)})
                    sale_order_line = self.env['sale.order.line'].create(order_line_vals)
                    sale_order_line.with_context(round=False)._compute_amount()
        return True

    def generate_shopify_shipping_lines(self, sale_order_id, order_response, instance_id):
        """
        This method was used for create shipping lines in sale order if found in shopify order response
        """
        order_number = order_response.get("order_number")
        for line in order_response.get("shipping_lines", []):
            carrier = self.env["delivery.carrier"].shopify_search_generate_delivery_carrier(line, instance_id)
            shipping_product_id = instance_id.shopify_shipping_product_id
            if carrier:
                self.write({"carrier_id": carrier.id})
                shipping_product_id = carrier.product_id
            if shipping_product_id:
                if float(line.get("price")) > 0.0:
                    order_line = self.crate_vals_for_sale_order_line(instance_id, 1,
                                                                     line.get('price'), shipping_product_id,
                                                                     sale_order_id, is_delivery=True)

                    order_line_vals = self.shopify_add_tax_in_sale_order_line(instance_id, line, order_response,
                                                                              line_vals=order_line,
                                                                              is_shipping=True)

                    sale_order_line = self.env['sale.order.line'].create(order_line_vals)
                    print(sale_order_line)

    def create_fulfillment_in_shopify(self, fulfillment_vals, sale_order, log_id):
        """
        fulfillment_vals = [{'notify_customer': False, 'line_items_by_fulfillment_order': [{'fulfillment_order_id': '6533175378176', 'fulfillment_order_line_items': [{'id': '13786285801728', 'quantity': 1}]}], 'tracking_info': {'company': 'shopify', 'number': '4561234567893', 'url': ''}}]
        """
        new_fulfillment = False
        fulfillment_result = False
        for new_fulfillment_vals in fulfillment_vals:
            try:
                new_fulfillment = shopify.fulfillment.FulfillmentV2(new_fulfillment_vals)
                fulfillment_result = new_fulfillment.save()
                if not fulfillment_result:
                    return False, fulfillment_result, new_fulfillment
            except ClientError as error:
                if hasattr(error,
                           "response") and error.response.code == 429 and error.response.msg == "Too Many Requests":
                    time.sleep(int(float(error.response.headers.get('Retry-After', 5))))
                    fulfillment_result = new_fulfillment.save()
            except Exception as error:
                message = "%s" % str(error)
                _logger.info(message)
                sale_order.instance_id.generate_shopify_process_line(shopify_operation_name='order_status',
                                                                     shopify_operation_type='export',
                                                                     shopify_instance=sale_order.instance_id,
                                                                     process_request_message=False,
                                                                     process_response_message=fulfillment_vals,
                                                                     shopify_operation_id=log_id,
                                                                     shopify_operation_message=message)
                self.write({'is_shopify_error': True})
                self.message_post(body=message)
                return True, fulfillment_result, new_fulfillment

        return False, fulfillment_result, new_fulfillment

    def prepare_vals_for_create_shopify_fulfillment(self, sale_order, picking, carrier_name,
                                                    line_items, notify_customer):
        """ This method is used to prepare a vals for the fulfillment.
            @return: fulfillment_vals
        """
        tracking_info = {}
        new_fulfillment_vals = []
        if carrier_name:
            tracking_info.update({"company": carrier_name})
        if picking.carrier_tracking_ref:
            tracking_info.update({"number": picking.carrier_tracking_ref, "url": picking.carrier_tracking_url or ''})
        fulfillment_vals = {
            "notify_customer": notify_customer,
            "line_items_by_fulfillment_order": [
                {
                    "fulfillment_order_id": picking.move_ids.sale_line_id[0].shopify_fulfillment_order_id,
                    "fulfillment_order_line_items": line_items
                }]
        }
        if tracking_info:
            fulfillment_vals.update({"tracking_info": tracking_info})
        _logger.info("FULFILLMENT VALS => {}".format(fulfillment_vals))
        new_fulfillment_vals.append(fulfillment_vals)

        # get service type product fulfillment data
        service_product_sale_line_ids = sale_order.order_line.filtered(
            lambda x: x.shopify_fulfillment_line_item_id and x.product_id.type == 'service' and not x.is_delivery)
        if service_product_sale_line_ids:
            service_fulfillment_data = []
            for line in service_product_sale_line_ids:
                service_fulfillment_vals = {
                    "notify_customer": notify_customer,
                    "line_items_by_fulfillment_order": [
                        {
                            "fulfillment_order_id": line.shopify_fulfillment_order_id,
                            "fulfillment_order_line_items": [{"id": line.shopify_fulfillment_line_item_id,
                                                              "quantity": int(line.product_qty)}]
                        }
                    ]
                }
                if tracking_info:
                    service_fulfillment_vals.update({"tracking_info": tracking_info})
                service_fulfillment_data.append(service_fulfillment_vals)
            new_fulfillment_vals.extend(service_fulfillment_data)
        _logger.info("NEW FULFILLMENT VALS => {}".format(new_fulfillment_vals))
        return new_fulfillment_vals

    def update_shopify_order_line_location(self, shopify_order_dict):
        shopify_location_obj = self.env['shopify.location']
        for order_line_dict in shopify_order_dict.get('line_items'):
            location_id = order_line_dict.get('location_id')
            order_line_id = self.order_line.search([('shopify_order_line_id', '=', order_line_dict.get('id'))])
            if order_line_id and location_id:
                shopify_location_id = shopify_location_obj.search([('shopify_location_id', '=', location_id), (
                    'instance_id', '=', self.instance_id.id)]) if location_id else False
                if location_id:
                    order_line_id.shopify_location_id = shopify_location_id.id
        return True

    def prepare_tracking_numbers_and_lines_for_fulfilment(self, picking):
        """
        Update Tracking Detail and Line Items List
        """
        shopify_line_ids = self.order_line.filtered(
            lambda l: l.shopify_order_line_id and l.product_id.type == "service" and not l.is_delivery and not
            l.is_gift_card_line).mapped("shopify_order_line_id") or []

        if picking.instance_id and not picking.instance_id.auto_fulfilled_gif_card_order:
            shopify_line_ids = self.order_line.filtered(
                lambda l: l.shopify_order_line_id and l.product_id.type == "service" and
                          not l.is_delivery).mapped("shopify_order_line_id") or []
        product_moves = picking.move_ids.filtered(
            lambda x: x.sale_line_id.product_id.id == x.product_id.id and x.state == "done")
        tracking_numbers = []
        line_items = []
        for move in product_moves.filtered(lambda line: line.product_id.detailed_type == 'product'):
            fulfillment_line_id = move.sale_line_id.shopify_fulfillment_line_item_id

            line_items.append({"id": fulfillment_line_id, "quantity": int(move.product_qty)})
            tracking_numbers.append(picking.carrier_tracking_ref or "")

        kit_product_order_line = picking.move_ids.filtered(
            lambda x: x.product_id.id != x.sale_line_id.product_id.id and x.state == "done").sale_line_id
        for kit_sale_line in kit_product_order_line:
            fulfillment_line_id = kit_sale_line.shopify_fulfillment_line_item_id
            line_items.append({"id": fulfillment_line_id, "quantity": int(kit_sale_line.product_qty)})
            tracking_numbers.append(picking.carrier_tracking_ref or "")

        for line in shopify_line_ids:
            quantity = sum(
                self.order_line.filtered(lambda l: l.shopify_order_line_id == line).mapped("product_uom_qty"))
            line_items.append({"id": line, "quantity": int(quantity)})
        return tracking_numbers, line_items

    def set_fulfillment_order_data(self, order, order_response=False):
        """
        2) Inside the Order Response Check Is there any Fulfillment Data If Yes Take It and Update the Order Line
        With Fulfillment Order ID and Fulfillment Line ID.

        [{'id': 6533175378176, 'shop_id': 68178510080, 'order_id': 5457602969856, 'assigned_location_id': 73413820672, 'request_status': 'unsubmitted', 'status': 'open', 'supported_actions': ['create_fulfillment', 'hold'], 'destination': {'id': 6405945524480, 'address1': '301', 'address2': 'Chandani Apartment, Near Moti tanki Chowk', 'city': 'Rajkot', 'company': None, 'country': 'India', 'email': 'support@vrajatechnologies.com', 'first_name': 'Bhautik', 'last_name': 'Shah', 'phone': None, 'province': 'Gujarat', 'zip': '360001'}, 'line_items': [{'id': 13786285801728, 'shop_id': 68178510080, 'fulfillment_order_id': 6533175378176, 'quantity': 1, 'line_item_id': 13609826124032, 'inventory_item_id': 46298188153088, 'fulfillable_quantity': 1, 'variant_id': 44194789818624}], 'international_duties': None, 'fulfill_at': '2024-01-02T04:00:00-05:00', 'fulfill_by': None, 'fulfillment_holds': [], 'created_at': '2024-01-02T04:43:19-05:00', 'updated_at': '2024-01-02T04:43:19-05:00',
        'delivery_method': {'id': 636332474624, 'method_type': 'shipping', 'min_delivery_date_time': None, 'max_delivery_date_time': None},
        'assigned_location': {'address1': None, 'address2': None, 'city': None, 'country_code': 'IN', 'location_id': 73413820672, 'name': 'Shop location', 'phone': None, 'province': None, 'zip': None}, 'merchant_requests': []}]
        """
        shopify_location_obj = self.env['shopify.location']
        fulfillments = shopify.FulfillmentOrders.find(order_id=order_response.get('id'))
        fulfillment_list = [fulfillment.to_dict() for fulfillment in fulfillments]
        if fulfillment_list:
            for fulfillment_dict in fulfillment_list:
                if fulfillment_dict.get('status', '') not in ['cancelled', 'incomplete']:
                    for line_item in fulfillment_dict.get('line_items'):
                        order_line = order.order_line.filtered(
                            lambda line: line.shopify_order_line_id == str(line_item.get('line_item_id')))
                        if order_line:
                            location_id = fulfillment_dict.get('assigned_location_id')
                            shopify_location_id = shopify_location_obj.search(
                                [('shopify_location_id', '=', location_id),
                                 ('instance_id', '=', order.instance_id.id)]) if location_id else False
                            order_line.write(
                                {'shopify_fulfillment_order_id': line_item.get('fulfillment_order_id'),
                                 'shopify_fulfillment_line_item_id': line_item.get('id'),
                                 'shopify_location_id': shopify_location_id and shopify_location_id.id or False})
        return True

    def fetch_shopify_order_response(self, shopify_instance, shopify_order, picking, log_id):
        """
        1) Fetch Order Response Data..If Order is Cancelled Or Refunded Or Already Fulfilled Stop the Process.
        Otherwise Return Order Response Data
        """
        sale_order = picking.sale_id
        try:
            shopify_order_dict = shopify_order.to_dict()
            if shopify_order_dict.get('cancelled_at') and shopify_order_dict.get('cancel_reason'):
                log_message = 'UPDATE ORDER STATUS: Shopify order {} is already cancelled in Shopify.'.format(
                    sale_order.name)
                picking.is_order_cancelled_in_shopify = True
                picking.message_post(body=log_message)
                shopify_instance.generate_shopify_process_line(shopify_operation_name='order_status',
                                                               shopify_operation_type='export',
                                                               shopify_instance=shopify_instance,
                                                               process_request_message=False,
                                                               process_response_message=shopify_order_dict,
                                                               shopify_operation_id=log_id,
                                                               shopify_operation_message=log_message)
                self._cr.commit()
                return True, shopify_order_dict
            if shopify_order_dict.get('fulfillment_status') == 'fulfilled':
                log_message = 'UPDATE ORDER STATUS: Shopify order {} is already Fulfilled in Shopify.'.format(
                    sale_order.name)
                picking.is_shopify_error = True
                picking.message_post(body=log_message)
                shopify_instance.generate_shopify_process_line(shopify_operation_name='order_status',
                                                               shopify_operation_type='export',
                                                               shopify_instance=shopify_instance,
                                                               process_request_message=False,
                                                               process_response_message=shopify_order_dict,
                                                               shopify_operation_id=log_id,
                                                               shopify_operation_message=log_message)
                self._cr.commit()
                return True, shopify_order_dict
            if shopify_order_dict.get('financial_status') == 'refunded':
                log_message = 'UPDATE ORDER STATUS: Order is Refunded in Shopify You cannot fulfill Shopify order {0}'.format(
                    sale_order.name)
                picking.message_post(body=log_message)
                shopify_instance.generate_shopify_process_line(shopify_operation_name='order_status',
                                                               shopify_operation_type='export',
                                                               shopify_instance=shopify_instance,
                                                               process_request_message=False,
                                                               process_response_message=shopify_order_dict,
                                                               shopify_operation_id=log_id,
                                                               shopify_operation_message=log_message)
                picking.is_shopify_error = True
                self._cr.commit()
                return True, shopify_order_dict
            return False, shopify_order_dict
        except Exception as Error:
            _logger.info("Error in Request of shopify order for the fulfilment. Error: %s", Error)
            return True, {}

    def close_shopify_order(self, shopify_order, odoo_order_id, close_order_after_fulfillment=True):
        shopify_order.close()
        odoo_order_id.write({'shopify_order_closed_at': fields.Datetime.now()})
        return True

    def update_order_status_in_shopify(self, shopify_instance, picking_ids=[], log_id=False):
        if not log_id:
            log_id = self.env['shopify.log'].generate_shopify_logs(shopify_operation_name='order_status',
                                                                   shopify_operation_type='export',
                                                                   instance=shopify_instance,
                                                                   shopify_operation_message='Process Started')
        for picking in picking_ids:
            carrier_name = picking.carrier_id.shopify_delivery_source or picking.carrier_id.shopify_delivery_code \
                           or picking.carrier_id.name or ''
            sale_order = picking.sale_id
            shopify_instance.connect_in_shopify()
            shopify_order = shopify.Order.find(sale_order.shopify_order_reference_id)
            is_error, shopify_order_dict = self.fetch_shopify_order_response(shopify_instance, shopify_order, picking,
                                                                             log_id)
            if is_error:
                continue
            order_lines = sale_order.order_line
            if order_lines and order_lines.filtered(
                    lambda s: s.product_id.detailed_type != 'service' and not s.shopify_order_line_id):
                log_message = (_(
                    "Order status could not be updated for order %s.\n- Possible reason can be, user may have done changes in order "
                    "manually, after the order was imported Due to that Shopify order line"
                    "reference is missing, which is used to update Shopify order status at Shopify store. ",
                    sale_order.name))
                shopify_instance.generate_shopify_process_line(shopify_operation_name='order_status',
                                                               shopify_operation_type='export',
                                                               shopify_instance=shopify_instance,
                                                               process_request_message=False,
                                                               process_response_message=shopify_order_dict,
                                                               shopify_operation_id=log_id,
                                                               shopify_operation_message=log_message)
                continue

            self.set_fulfillment_order_data(sale_order, shopify_order_dict)

            tracking_numbers, line_items = sale_order.prepare_tracking_numbers_and_lines_for_fulfilment(picking)

            if not line_items:
                message = "No Order Line Found for the update order shipping status for order [%s]" \
                          % sale_order.name
                _logger.info(message)
                shopify_instance.generate_shopify_process_line(shopify_operation_name='order_status',
                                                               shopify_operation_type='export',
                                                               shopify_instance=shopify_instance,
                                                               process_request_message=False,
                                                               process_response_message=shopify_order_dict,
                                                               shopify_operation_id=log_id,
                                                               shopify_operation_message=message)
                continue

            # shopify_location_id = self.search_shopify_location_for_update_order_status(sale_order, shopify_instance, log_id)
            #
            # if not shopify_location_id:
            #     continue

            fulfillment_vals = self.prepare_vals_for_create_shopify_fulfillment(sale_order, picking, carrier_name,
                                                                                line_items,
                                                                                shopify_instance.notify_customer)

            _logger.info("FROM MAIN METHOD BEFORE POST SALE ORDER: {0}".format(sale_order.name))

            is_error, fulfillment_result, new_fulfillment = self.create_fulfillment_in_shopify(fulfillment_vals,
                                                                                               sale_order, log_id)

            if is_error:
                shopify_instance.generate_shopify_process_line(shopify_operation_name='order_status',
                                                               shopify_operation_type='export',
                                                               shopify_instance=shopify_instance,
                                                               process_request_message=fulfillment_vals,
                                                               process_response_message=False,
                                                               shopify_operation_id=log_id,
                                                               shopify_operation_message=fulfillment_result)
                continue

            if new_fulfillment:
                shopify_fulfillment_result = xml_to_dict(new_fulfillment.to_xml())
                if shopify_fulfillment_result:
                    fulfillment_id = shopify_fulfillment_result.get('fulfillment').get('id') or ''

                picking.write({'updated_status_in_shopify': True, 'shopify_fulfillment_id': fulfillment_id})
                if True not in [True if line.get('fulfillment_status') == 'partial' else False for line in
                                shopify_fulfillment_result.get('fulfillment').get('line_items')]:
                    self.close_shopify_order(shopify_order, sale_order)
            self._cr.commit()

        if not log_id.shopify_operation_line_ids:
            log_id.unlink()
        return True

    def import_cancel_order_from_shopify_to_odoo(self,instance_id):
        instance_id.test_shopify_connection()
        from_date = fields.Datetime.now() - timedelta(10)
        to_date = fields.Datetime.now()
        try:
            cancel_order_list = (
                shopify.Order().find(status='cancelled', fulfillment_status='unshipped', processed_at_min=from_date,
                                     processed_at_max=to_date, limit=250))
        except Exception as error:
            _logger.info(error)
        if cancel_order_list:
            res_id_list = self.create_shopify_order_queue_job(instance_id, cancel_order_list)
