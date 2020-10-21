from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError
from datetime import datetime
from odoo import fields, models, _
import requests
import logging
import json

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
    
    def create_skuvault_operation_detail(self, skuvault_operation, operation_type, req_data, response_data, operation_id,
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
            if response_data.status_code in [200, 201]:
                _logger.info("Get Successfully Response From {}".format(api_url))
                response_data = response_data.json()
                return response_data
            else:
                raise ValidationError(_("Getting some issue from {}".format(api_url)))

        except Exception as error:
            raise ValidationError(_("Getting some issue from {}".format(api_url)))

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

    def get_item_quantities(self, afterdate=False, beforedate=False):
        if not self.skuvault_tenantToken and self.skuvault_UserToken:
            raise ValidationError(_("Please generate authentication code"))
        api_url = "%s/api/inventory/getItemQuantities" % (self.skuvault_api_url)
        operation_id = self.env['skuvault.operation'].create({'skuvault_operation':'product','skuvault_operation_type':'import','warehouse_id':self.id,'company_id':self.env.user.company_id.id,'skuvault_message':'Processing...'})
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
                        process_message = ">>> Stock Quant Created Product Name : {0} and Quantity: {1} ".format(product_id.name,available_qty)
                        _logger.info(process_message)
                        self.create_skuvault_operation_detail('product','import',data,items_data,operation_id,self,False,process_message)
                    else:
                        #total_available_quantity = available_qty + quant_id.reserved_quantity
                        if quant_id.quantity != available_qty:
                            old_qty = quant_id.quantity
                            quant_id.sudo().write({'inventory_quantity': available_qty, 'quantity': available_qty})
                            process_message = ">>> Stock Quant Updated Product Name : {0} and OLD Quantity: {1} and New Qty : {2}".format(product_id.name,old_qty,available_qty)
                            _logger.info(process_message)
                            self.create_skuvault_operation_detail('product','import',data,items_data,operation_id,self,False,process_message)
        except Exception as error:
            _logger.info(error)
            self.create_skuvault_operation_detail('product','import',False,False,operation_id,self,True,error)

    def skuvault_inventory_crone(self):
        for current_record_id in self.search([]):
            if current_record_id.skuvault_UserToken and current_record_id.skuvault_tenantToken:
                before_date = datetime.now() + relativedelta(hours=10)
                after_date = before_date - relativedelta(days=1)
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
        operation_id = self.env['skuvault.operation'].create({'skuvault_operation':'product','skuvault_operation_type':'import','warehouse_id':self.id,'company_id':self.env.user.company_id.id,'skuvault_message':'Processing...'})
        try:
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            before_date = datetime.now() + relativedelta(hours=10)
            after_date = before_date - relativedelta(days=4)
            request_data = {
                "ModifiedAfterDateTimeUtc": "{}".format(after_date),#self.skuvault_modify_after_date.strftime("%Y-%m-%dT%H:%M:%S")
                "ModifiedBeforeDateTimeUtc": "{}".format(before_date), #self.skuvault_modify_before_date.strftime("%Y-%m-%dT%H:%M:%S")
                "TenantToken": "{}".format(self.skuvault_tenantToken),
                "UserToken": "{}".format(self.skuvault_UserToken)
            }
            response_data = requests.post(url=api_url, data=json.dumps(request_data), headers=headers)
            if response_data.status_code in [200, 201]:
                _logger.info(">>> get successfully response from {}".format(api_url))
                response_data = response_data.json()
                if response_data.get('Products'):
                    for product_data in response_data.get('Products'):
                        product_id = self.env['product.template'].sudo().search(
                            [('default_code', '=', '{}'.format(product_data.get('Sku')))])
                        if product_id:
                            product_id.write({
                                            'description':product_data.get('Description'),
                                            'lst_price':product_data.get('SalePrice'),
                                            'weight':product_data.get('WeightValue'),
                                            'standard_price':product_data.get('Cost')})
                            for attribute_data in product_data.get('Attributes'):
                                if attribute_data.get('Name') == 'Category':
                                    product_id.write({'x_studio_category': attribute_data.get('Value')})
                                elif attribute_data.get('Name') == 'Alt Manufacturer':
                                    product_id.write({'x_studio_manufacturer': attribute_data.get('Value')})
                                elif attribute_data.get('Name') == 'Alt Number':
                                    product_id.write({'x_studio_alternate_number': attribute_data.get('Value')})
                                elif attribute_data.get('Name') == 'Date Code':
                                    product_id.write({'x_studio_date_code_1': attribute_data.get('Value')})
                                elif attribute_data.get('Name') == 'Origin':
                                    product_id.write({'x_studio_origin_code': attribute_data.get('Value')})
                                elif attribute_data.get('Name') == 'Condition':
                                    product_id.write({'x_studio_condition_1': attribute_data.get('Value')})
                                elif attribute_data.get('Name') == 'Package':
                                    product_id.write({'x_studio_package': attribute_data.get('Value')})
                                elif attribute_data.get('Name') == 'RoHS':
                                    product_id.write({'x_studio_rohs': attribute_data.get('Value')})
                                process_message = "Product Updated {0}".format(product_id)
                        else:
                            process_message = "Product Not Found"
                        self.create_skuvault_operation_detail('product','import',request_data,product_data,operation_id,self,False,process_message)
                        self._cr.commit()
                else:
                    _logger.info('>>>>> Product not found in response ')
            else:
                process_message = ">>>>> get some error from{}".format(response_data.text)
                _logger.info(process_message)
                self.create_skuvault_operation_detail('product','import',False,False,operation_id,self,False,process_message)
        except Exception as error:
            _logger.info(error)
            process_message = "{}".format(error)
            self.create_skuvault_operation_detail('product','import',False,False,operation_id,self,False,process_message)
