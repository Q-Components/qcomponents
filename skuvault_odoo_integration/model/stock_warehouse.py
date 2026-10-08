from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError, UserError
from datetime import datetime
from odoo import api, fields, models, _
import requests
import logging
import json
import time
_logger = logging.getLogger(__name__)


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    skuvault_api_url = fields.Char(string="Skuvault API URL", help="Enter api url pf skuvault",
                                   default="https://app.skuvault.com")
    skuvault_email_id = fields.Char(string="Skuvault Email Id", help="Enter your skuvault account's email address")
    skuvault_password = fields.Char(string="Skuvault Password", help="Enter your skuvault account's password")

    skuvault_tenantToken = fields.Char(string='Skuvault tenantTokne', readonly=True)
    skuvault_UserToken = fields.Char(string='Skuvault UserToken', readonly=True)

    skuvault_modify_after_date = fields.Datetime(string="Skuvault After Date", help="Select after date")
    skuvault_modify_before_date = fields.Datetime(string="Skuvault Before Date", help="Select before date")

    use_skuvault_warehouse_management = fields.Boolean(copy=False, string="Are You Using Skuvault?",
                                                       help="If use SKUVAULT warehouse management than value set TRUE.",
                                                       default=False)

    skuvault_batch_size = fields.Integer(string="Batch Size", default=100)
    skuvault_inventory_page_size = fields.Integer(string="API Page Size", default=1000,
                                                  help="Products fetched from SkuVault per API call.")
    skuvault_inventory_page = fields.Integer(string="Next API Page", default=0, copy=False)

    def create_skuvault_operation_detail(self, skuvault_operation, operation_type, req_data, response_data,
                                         operation_id,
                                         warehouse_id=False, fault_operation=False, process_message=False):
        skuvault_operation_details_obj = self.env['skuvault.operation.details']
        vals = {
            'skuvault_operation': skuvault_operation,
            'skuvault_operation_type': operation_type,
            'request_message': '{}'.format(req_data),
            'response_message': '{}'.format(response_data),
            'operation_id': operation_id.id,
            'warehouse_id': warehouse_id and warehouse_id.id or False,
            'fault_operation': fault_operation,
            'process_message': process_message,
        }
        operation_detail_id = skuvault_operation_details_obj.create(vals)
        return operation_detail_id

    def skuvault_api_calling(self, api_url, request_data):
        """
        :param api_url:
        :param request_data:
        :return: this method return api response
        """
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        try:
            response_data = requests.post(url=api_url, data=json.dumps(request_data), headers=headers)
            _logger.info("{0}{1}{2}".format(response_data.status_code,response_data,headers))
            if response_data.status_code in [200, 201]:
                _logger.info("Get Successfully Response From {}".format(api_url))
                response_data = response_data.json()
                return response_data
            else:
                raise ValidationError(_("Getting some issue from {}".format(response_data.content)))

        except Exception as error:
            raise ValidationError(_("Getting Error {0}".format(api_url)))

    def get_authentication_tokens(self):
        api_url = "%s/api/gettokens" % (self.skuvault_api_url)
        data = {
            "Email": "{}".format(self.skuvault_email_id),
            "Password": "{}".format(self.skuvault_password)
        }
        try:
            response_data = self.skuvault_api_calling(api_url, data)
            _logger.info("{}".format(response_data))
            if not response_data.get('TenantToken') and response_data.get('UserToken'):
                raise ValidationError(_("token not found in response"))
            self.skuvault_tenantToken = response_data.get('TenantToken')
            self.skuvault_UserToken = response_data.get('UserToken')
            _logger.info("Token Updated")
        except Exception as error:
            raise ValidationError(_(error))

    def get_inventory_by_location(self):
        if not self.skuvault_tenantToken and self.skuvault_UserToken:
            raise ValidationError(_("Please generate authentication code"))
        api_url = "%s/api/inventory/getInventoryByLocation" % (self.skuvault_api_url)
        operation_id = self.env['skuvault.operation'].create(
            {'skuvault_operation': 'product', 'skuvault_operation_type': 'import', 'warehouse_id': self.id,
             'company_id': self.env.user.company_id.id, 'skuvault_message': 'Processing...'})
        total_pages = 100
        for pageNumber in total_pages:
            data = {
                "TenantToken": "{}".format(self.skuvault_tenantToken),
                "UserToken": "{}".format(self.skuvault_UserToken),
                "pagesize": 10000,
                "PageNumber": pageNumber
            }
        try:
            response_data = self.skuvault_api_calling(api_url, data)
            items_list = response_data.get('Items')
            if len(items_list) == 0:
                raise ValidationError("Product Not Found in the Response")
            _logger.info(">>>> Product data {}".format(items_list))
            for items_data in items_list:
                product_id = self.env['product.product'].search([('default_code', '=', items_data.get('Sku'))], limit=1)
                available_qty = items_data.get('AvailableQuantity')
                if product_id:
                    quant_id = self.env['stock.quant'].with_user(1).search(
                        [('product_id', '=', product_id.id), ('location_id', '=', self.lot_stock_id.id)], limit=1)
                    if not quant_id:
                        vals = {'product_tmpl_id': product_id.product_tmpl_id.id, 'location_id': self.lot_stock_id.id,
                                'inventory_quantity': available_qty, 'product_id': product_id.id,
                                'quantity': available_qty}
                        self.env['stock.quant'].with_user(1).create(vals)
                        process_message = ">>> Stock Quant Created Product Name : {0} and Quantity: {1} ".format(
                            product_id.name, available_qty)
                        _logger.info(process_message)
                        self.create_skuvault_operation_detail('product', 'import', data, items_data, operation_id, self,
                                                              False, process_message)
                        self._cr.commit()
                    else:
                        # total_available_quantity = available_qty + quant_id.reserved_quantity
                        if quant_id.quantity != available_qty:
                            old_qty = quant_id.quantity
                            quant_id.sudo().write({'inventory_quantity': available_qty, 'quantity': available_qty})
                            process_message = ">>> Stock Quant Updated Product Name : {0} and OLD Quantity: {1} and New Qty : {2}".format(
                                product_id.name, old_qty, available_qty)
                            _logger.info(process_message)
                            self.create_skuvault_operation_detail('product', 'import', data, items_data, operation_id,
                                                                  self, False, process_message)
                            self._cr.commit()
        except Exception as error:
            _logger.info(error)
            self.create_skuvault_operation_detail('product', 'import', False, False, operation_id, self, True, error)

    def get_item_quantities(self, afterdate=False, beforedate=False,):
        """
        :param batch_qty_by_sku: optional dict {sku: available_qty}. When given (batch processing), the
            SkuVault API is NOT called again and only these SKUs are searched/updated in Odoo.
        """
        if not self.skuvault_tenantToken and self.skuvault_UserToken:
            raise ValidationError(_("Please generate authentication code"))
        api_url = "%s/api/inventory/getItemQuantities" % (self.skuvault_api_url)
        operation_id = self.env['skuvault.operation'].create(
            {'skuvault_operation': 'product', 'skuvault_operation_type': 'import', 'warehouse_id': self.id,
             'company_id': self.env.user.company_id.id, 'skuvault_message': 'Processing...'})
        # {sku: False} when Odoo inventory was updated, {sku: 'reason'} when it was not
        update_result = {}
        if afterdate and beforedate:
            data = {
                "ModifiedAfterDateTimeUtc": "{}".format(afterdate),
                "ModifiedBeforeDateTimeUtc": "{}".format(beforedate),
                "TenantToken": "{}".format(self.skuvault_tenantToken),
                "UserToken": "{}".format(self.skuvault_UserToken),
                "pagesize": 1000
            }
        else:
            data = {
                "ModifiedAfterDateTimeUtc": "{}".format(self.skuvault_modify_after_date),
                "ModifiedBeforeDateTimeUtc": "{}".format(self.skuvault_modify_before_date),
                "TenantToken": "{}".format(self.skuvault_tenantToken),
                "UserToken": "{}".format(self.skuvault_UserToken),
                "pagesize": 1000
            }
        try:
            response_data = self.skuvault_api_calling(api_url, data)
            items_list = response_data.get('Items')
            if len(items_list) == 0:
                raise ValidationError("Product Not Found in the Response")
            _logger.info(">>>> Product data {}".format(items_list))
            pending_deliveries = self.env['stock.picking'].search([
                ('picking_type_code', '=', 'outgoing'),
                ('state', '=', 'assigned'),
                ('picking_type_id.warehouse_id', '=', self.id),
            ])
            delivery_pending_product_ids = pending_deliveries.move_ids.product_id.ids
            for items_data in items_list:
                product_id = self.env['product.product'].search([('default_code', '=', items_data.get('Sku'))], limit=1)
                if not product_id:
                    update_result[items_data.get('Sku')] = "Product not found in Odoo."
                    # continue
                    _logger.info("Product Not Found : {0}".format(items_data.get('Sku')))
                    product_api_url = "%s/api/products/getProduct" % (self.skuvault_api_url)
                    try:
                        headers = {
                            'Content-Type': 'application/json',
                            'Accept': 'application/json'
                        }
                        before_date = datetime.now() + relativedelta(hours=4) if not self.skuvault_modify_before_date else self.skuvault_modify_before_date
                        after_date = before_date - relativedelta(days=4) if not self.skuvault_modify_after_date else self.skuvault_modify_after_date
                        product_request_data = {
                            "ProductCode":items_data.get('Code'),
                            "TenantToken": "{}".format(self.skuvault_tenantToken),
                            "UserToken": "{}".format(self.skuvault_UserToken)
                        }
                        _logger.info("{0}{1}".format(product_api_url,product_request_data))
                        response_data = requests.post(url=product_api_url, data=json.dumps(product_request_data), headers=headers)
                        if response_data.status_code in [200, 201]:
                            product_response_data = response_data.json()
                            _logger.info(">>> get successfully response from {}".format(product_response_data))
                            if product_response_data.get('Product'):
                                product_data = product_response_data.get('Product')
                                product_tmpl_id = self.env['product.template'].sudo().search([('default_code', '=',product_data.get('Sku'))])
                                vals = {
                                    'description': product_data.get('Description'),
                                    'default_code':product_data.get('Sku'),
                                    'name':product_data.get('PartNumber','') or product_data.get('Sku'),
                                    #'lst_price': product_data.get('SalePrice'),
                                    'weight': product_data.get('WeightValue'),
                                    'type':'consu',
                                    'supplier_name':product_data.get('Supplier'),
                                    'standard_price': product_data.get('Cost')}
                                for attribute_data in product_data.get('Attributes'):
                                    if attribute_data.get('Name') == 'Category' and attribute_data.get('Value'):
                                        vals.update({'x_studio_category': attribute_data.get('Value')})
                                    elif attribute_data.get('Name') == 'Alt Manufacturer' and attribute_data.get('Value'):
                                        vals.update({'x_studio_manufacturer': attribute_data.get('Value')})
                                    elif attribute_data.get('Name') == 'Alt Number' and attribute_data.get('Value'):
                                        vals.update({'x_studio_alternate_number': attribute_data.get('Value')})
                                    elif attribute_data.get('Name') == 'Date Code' and attribute_data.get('Value'):
                                        vals.update({'x_studio_date_code_1': attribute_data.get('Value')})
                                    elif attribute_data.get('Name') == 'Origin' and attribute_data.get('Value'):
                                        vals.update({'x_studio_origin_code': attribute_data.get('Value')})
                                    elif attribute_data.get('Name') == 'Condition' and attribute_data.get('Value'):
                                        vals.update({'x_studio_condition_1': attribute_data.get('Value')})
                                    elif attribute_data.get('Name') == 'Package' and attribute_data.get('Value'):
                                        vals.update({'x_studio_package': attribute_data.get('Value')})
                                    elif attribute_data.get('Name') == 'RoHS' and attribute_data.get('Value'):
                                        vals.update({'x_studio_rohs': attribute_data.get('Value')})
                                if not product_tmpl_id:
                                    product_tmpl_id = self.env['product.template'].create(vals)
                                    product_id = product_tmpl_id.product_variant_id
                                    process_message = "Product Created:{0} Name : {1}".format(product_id.default_code,product_id.name)
                                self.sudo().create_skuvault_operation_detail('product', 'import', product_request_data, product_data,
                                                                      operation_id, self, False, process_message)
                                self._cr.commit()
                        else:
                            process_message = ">>>>> get some error from{}".format(response_data.text)
                            _logger.info(process_message)
                            self.sudo().create_skuvault_operation_detail('product', 'import', False, False, operation_id, self, False,
                                                                  process_message)
                    except Exception as error:
                        _logger.info(error)
                        process_message = "{}".format(error)
                        self.sudo().create_skuvault_operation_detail('product', 'import', False, False, operation_id, self, False,
                                                              process_message)
                # create inventory line
                stock_quant_obj = self.env['stock.quant']
                new_quantity = 0
                location = self.lot_stock_id
                if product_id.id not in delivery_pending_product_ids and location:
                # if product_id and location:
                    new_quantity = float(items_data.get('AvailableQuantity'))
                    stock_quant = stock_quant_obj.search([('product_id', '=', product_id.id),
                                                          ('location_id', '=', location.id)], limit=1)
                    if stock_quant:
                        # new_quantity = stock_quant.quantity + new_quantity
                        stock_quant.update({'inventory_quantity': new_quantity})
                        stock_quant.action_apply_inventory()
                        # stock_quant._update_available_quantity(product, location, float(qty_adjust), lot_id=None,
                        #                                        package_id=None, owner_id=None, in_date=None)
                    else:
                        stock_quant_obj.create({
                            'location_id': location.id,
                            'product_id': product_id.id,
                            'inventory_quantity': new_quantity
                        }).action_apply_inventory()
                    update_result[items_data.get('Sku')] = False
                else:
                    update_result[items_data.get('Sku')] = \
                        "Inventory not updated: no done outgoing delivery found for this product in the warehouse."

                process_message = ">>> Inventory Line Created Product Name : {0} and Quantity: {1} ".format(
                    product_id.name, new_quantity)
                _logger.info(process_message)
                self.create_skuvault_operation_detail('product', 'import', data, items_data, operation_id, self,
                                                      False, process_message)
            operation_id.skuvault_message = "Inventory Update Process Completed Between {0} To {1}".format(beforedate,afterdate)
        except Exception as error:
            _logger.info(error)
            self.create_skuvault_operation_detail('product', 'import', False, False, operation_id, self, True, error)
        return update_result

    def skuvault_inventory_crone(self):
        for current_record_id in self.search([]):
            if current_record_id.skuvault_UserToken and current_record_id.skuvault_tenantToken:
                before_date = datetime.now() + relativedelta(hours=10)
                after_date = before_date - relativedelta(days=2)
                current_record_id.get_item_quantities(afterdate=after_date, beforedate=before_date)
            else:
                _logger.info(">>>> Authentication token not found")

    def skuvault_import_product_crone(self):
        for current_record_id in self.search([]):
            if current_record_id.skuvault_UserToken and current_record_id.skuvault_tenantToken:
                current_record_id.import_product_from_skuvault()
            else:
                _logger.info(">>>> Authentication token not found")

    def import_product_from_skuvault(self):
        """
        :return: this method return product from skuvault
        """
        api_url = "%s/api/products/getProducts" % (self.skuvault_api_url)
        operation_id = self.env['skuvault.operation'].create(
            {'skuvault_operation': 'product', 'skuvault_operation_type': 'import', 'warehouse_id': self.id,
             'company_id': self.env.user.company_id.id, 'skuvault_message': 'Processing...'})
        try:
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            before_date = datetime.now() + relativedelta(hours=4) if not self.skuvault_modify_before_date else self.skuvault_modify_before_date
            after_date = before_date - relativedelta(days=4) if not self.skuvault_modify_after_date else self.skuvault_modify_after_date
            request_data = {
                "ModifiedAfterDateTimeUtc": "{}".format(after_date),
                # self.skuvault_modify_after_date.strftime("%Y-%m-%dT%H:%M:%S")
                "ModifiedBeforeDateTimeUtc": "{}".format(before_date),
                # self.skuvault_modify_before_date.strftime("%Y-%m-%dT%H:%M:%S")
                "TenantToken": "{}".format(self.skuvault_tenantToken),
                "UserToken": "{}".format(self.skuvault_UserToken)
            }
            response_data = requests.post(url=api_url, data=json.dumps(request_data), headers=headers)
            if response_data.status_code in [200, 201]:
                _logger.info(">>> get successfully response from {}".format(api_url))
                response_data = response_data.json()
                if response_data.get('Products'):
                    for product_data in response_data.get('Products'):
                        product_id = self.env['product.template'].sudo().search([('default_code', '=',product_data.get('Sku'))])
                        vals = {
                            'description': product_data.get('Description'),
                            'default_code':product_data.get('Sku'),
                            'name':product_data.get('PartNumber','') or product_data.get('Sku'),
                            #'lst_price': product_data.get('SalePrice'),
                            'weight': product_data.get('WeightValue'),
                            'type':'consu',
                            'standard_price': product_data.get('Cost')}
                        for attribute_data in product_data.get('Attributes'):
                            if attribute_data.get('Name') == 'Category' and attribute_data.get('Value'):
                                vals.update({'x_studio_category': attribute_data.get('Value')})
                            elif attribute_data.get('Name') == 'Alt Manufacturer' and attribute_data.get('Value'):
                                vals.update({'x_studio_manufacturer': attribute_data.get('Value')})
                            elif attribute_data.get('Name') == 'Alt Number' and attribute_data.get('Value'):
                                vals.update({'x_studio_alternate_number': attribute_data.get('Value')})
                            elif attribute_data.get('Name') == 'Date Code' and attribute_data.get('Value'):
                                vals.update({'x_studio_date_code_1': attribute_data.get('Value')})
                            elif attribute_data.get('Name') == 'Origin' and attribute_data.get('Value'):
                                vals.update({'x_studio_origin_code': attribute_data.get('Value')})
                            elif attribute_data.get('Name') == 'Condition' and attribute_data.get('Value'):
                                vals.update({'x_studio_condition_1': attribute_data.get('Value')})
                            elif attribute_data.get('Name') == 'Package' and attribute_data.get('Value'):
                                vals.update({'x_studio_package': attribute_data.get('Value')})
                            elif attribute_data.get('Name') == 'RoHS' and attribute_data.get('Value'):
                                vals.update({'x_studio_rohs': attribute_data.get('Value')})
                        if product_id:
                            vals.pop('type')
                            product_id.write(vals)
                            process_message = "Product Updated {0}".format(product_id.name)
                        else:
                            product_id = self.env['product.template'].create(vals)
                            process_message = "Product Created : {0}".format(product_id.name)
                        self.create_skuvault_operation_detail('product', 'import', request_data, product_data,
                                                              operation_id, self, False, process_message)
                        self._cr.commit()
                else:
                    _logger.info('>>>>> Product not found in response ')
            else:
                process_message = ">>>>> get some error from{}".format(response_data.text)
                _logger.info(process_message)
                self.create_skuvault_operation_detail('product', 'import', False, False, operation_id, self, False,
                                                      process_message)
            operation_id.sudo().write({'skuvault_message' :"Product Imported Sucessfully Between {0} TO {1}".format(before_date,after_date)})
            self.skuvault_modify_before_date = False
            self.skuvault_modify_after_date = False
        except Exception as error:
            _logger.info(error)
            process_message = "{}".format(error)
            self.create_skuvault_operation_detail('product', 'import', False, False, operation_id, self, False,
                                                  process_message)

    def _skuvault_fetch_page(self):
        """Fetch one page of SkuVault quantities. Returns {sku: available_qty}."""
        self.ensure_one()
        api_url = "%s/api/inventory/getItemQuantities" % self.skuvault_api_url

        data = {
            # "ModifiedAfterDateTimeUtc":"{}".format(self.skuvault_modify_after_date) ,
            # "ModifiedBeforeDateTimeUtc":"{}".format(self.skuvault_modify_before_date) ,
            "TenantToken": "{}".format(self.skuvault_tenantToken),
            "UserToken": "{}".format(self.skuvault_UserToken),
            "PageNumber": self.skuvault_inventory_page,
            "pagesize": 10000,
        }
        response = self.skuvault_api_calling(api_url, data)
        items = response.get('Items') or []
        return {item['Sku']: float(item.get('AvailableQuantity') or 0.0) for item in items if item.get('Sku')}

    def skuvault_create_batches(self):
        """One API page -> batches of `skuvault_batch_size` products (500 products = 5 batches of 100).
        SKUs which already have a batch line are skipped, so a product is never queued twice."""
        self.ensure_one()
        if not (self.skuvault_tenantToken and self.skuvault_UserToken):
            raise UserError(_("Please generate the authentication token first."))
        qty_by_sku = self._skuvault_fetch_page()
        if not qty_by_sku:
            return self.env['skuvault.inventory.batch']

        queued = set(self.env['skuvault.inventory.batch.line'].search(
            [('warehouse_id', '=', self.id), ('sku', 'in', list(qty_by_sku))]).mapped('sku'))
        new_skus = [sku for sku in qty_by_sku if sku not in queued]
        product_by_sku = {}
        for product in self.env['product.product'].search([('default_code', 'in', new_skus)]):
            product_by_sku.setdefault(product.default_code, product)
        size = self.skuvault_batch_size or 100
        batches = self.env['skuvault.inventory.batch']
        for i in range(0, len(new_skus), size):
            batches |= batches.create({
                'warehouse_id': self.id,
                'line_ids': [(0, 0, {
                    'warehouse_id': self.id,
                    'sku': sku,
                    'available_qty': qty_by_sku[sku],
                    'product_id': product_by_sku[sku].id if sku in product_by_sku else False,
                }) for sku in new_skus[i:i + size]],
            })
        self.skuvault_inventory_page += 1
        return batches

    def action_create_inventory_batch(self):
        self.ensure_one()
        batches = self.skuvault_create_batches()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Skuvault Inventory Batch"),
                'message': _("%s batch(es) created.", len(batches)),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    def action_view_inventory_batches(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Inventory Batches"),
            'res_model': 'skuvault.inventory.batch',
            'view_mode': 'list,form',
            'domain': [('warehouse_id', '=', self.id)],
        }

    @api.model
    def skuvault_cron_create_batches(self, max_pages=55):
        """CRON 1: create batches from the SkuVault response."""
        for warehouse in self.search([('use_skuvault_warehouse_management', '=', True)]):
            if not (warehouse.skuvault_tenantToken and warehouse.skuvault_UserToken):
                continue
            for _page in range(max_pages):
                try:
                    batches = warehouse.skuvault_create_batches()
                    self.env.cr.commit()
                except Exception as error:
                    self.env.cr.rollback()
                    _logger.error("Skuvault batch creation failed for %s: %s", warehouse.name, error)
                    break
                if not batches:
                    break
