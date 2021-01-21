# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta
from datetime import datetime
import logging
from odoo import models
import requests
import json
import time

_logger = logging.getLogger(__name__)

class PorductProduct(models.Model):
    _inherit = 'product.product'

    def update_inventory_from_variant_manually_to_odoo(self):
        warehouse_id = self.env['stock.warehouse'].search([('use_skuvault_warehouse_management','=',True)])
        if not warehouse_id.skuvault_tenantToken and warehouse_id.skuvault_UserToken:
            raise ValidationError(_("Please generate authentication code"))
        api_url = "%s/api/inventory/getItemQuantities" % (warehouse_id.skuvault_api_url)
        operation_id = self.env['skuvault.operation'].create(
            {'skuvault_operation': 'product', 'skuvault_operation_type': 'import', 'warehouse_id': warehouse_id.id,
             'company_id': self.env.user.company_id.id, 'skuvault_message': 'Processing...'})
        inventory_name = "SKuvault_Inventory_%s" % (str(datetime.now().date()))
        inventory_vals = {
            'name': inventory_name,
            'location_ids': [(6, 0, warehouse_id.lot_stock_id.ids)],
            'date': time.strftime("%Y-%m-%d %H:%M:%S"),
            'company_id': warehouse_id.company_id.id,
            'prefill_counted_quantity': 'zero'
        }
        inventory_id = self.env['stock.inventory'].sudo().create(inventory_vals)
        _logger.info("Inventory Created : {}".format(inventory_id))
        for product_id in self:
            data = {
                "TenantToken": "{}".format(warehouse_id.skuvault_tenantToken),
                "UserToken": "{}".format(warehouse_id.skuvault_UserToken),
                "ProductCodes":[product_id.default_code]
            }
            try:
                response_data = warehouse_id.skuvault_api_calling(api_url, data)
                items_list = response_data.get('Items')
                if len(items_list) == 0:
                    raise ValidationError("Product Not Found in the Response")
                _logger.info(">>>> Product data {}".format(items_list))
                inventroy_line_obj = self.env['stock.inventory.line']
                for items_data in items_list:
                    product_api_url = "%s/api/products/getProduct" % (self.skuvault_api_url)
                    try:
                        headers = {
                            'Content-Type': 'application/json',
                            'Accept': 'application/json'
                        }
                        product_request_data = {
                            "ProductCode":product_id.default_code,
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
                                product_tmpl_id = self.env['product.template'].sudo().search([('default_code', '=',product_data.get('Sku'))],limit=1)
                                vals = {
                                    'description': product_data.get('Description'),
                                    'default_code':product_data.get('Sku'),
                                    'name':product_data.get('PartNumber','') or product_data.get('Sku'),
                                    'lst_price': product_data.get('SalePrice'),
                                    'weight': product_data.get('WeightValue'),
                                    'type':'product',
                                    'standard_price': product_data.get('Cost')}
                                for attribute_data in product_data.get('Attributes'):
                                    if attribute_data.get('Name') == 'Category':
                                        vals.update({'x_studio_category': attribute_data.get('Value')})
                                    elif attribute_data.get('Name') == 'Alt Manufacturer':
                                        vals.update({'x_studio_manufacturer': attribute_data.get('Value')})
                                    elif attribute_data.get('Name') == 'Alt Number':
                                        vals.update({'x_studio_alternate_number': attribute_data.get('Value')})
                                    elif attribute_data.get('Name') == 'Date Code':
                                        vals.update({'x_studio_date_code_1': attribute_data.get('Value')})
                                    elif attribute_data.get('Name') == 'Origin':
                                        vals.update({'x_studio_origin_code': attribute_data.get('Value')})
                                    elif attribute_data.get('Name') == 'Condition':
                                        vals.update({'x_studio_condition_1': attribute_data.get('Value')})
                                    elif attribute_data.get('Name') == 'Package':
                                        vals.update({'x_studio_package': attribute_data.get('Value')})
                                    elif attribute_data.get('Name') == 'RoHS':
                                        vals.update({'x_studio_rohs': attribute_data.get('Value')})
                                
                                product_tmpl_id.write(vals)
                            else:
                                process_message = ">>>>> get some error from{}".format(response_data.text)
                                _logger.info(process_message)
                                self.sudo().create_skuvault_operation_detail('product', 'import', False, False, operation_id, self, False,process_message)
                    except Exception as error:
                        _logger.info(error)
                        process_message = "{}".format(error)
                        self.sudo().create_skuvault_operation_detail('product', 'import', False, False, operation_id, self, False,process_message)
                    # create inventory line
                    quant_ids = self.env['stock.quant'].sudo().search([('product_id','=',product_id.id),('location_id','!=',8),('location_id.usage','=','internal')])
                    if quant_ids:
                        quant_ids.sudo().unlink()
                    available_qty = items_data.get('AvailableQuantity')
                    inventroy_line_obj.sudo().create({'product_id': product_id.id,
                                                      'inventory_id': inventory_id and inventory_id.id,
                                                      'location_id': warehouse_id.lot_stock_id.id,
                                                      'product_qty': items_data.get('AvailableQuantity', 0.0),
                                                      'product_uom_id': product_id.uom_id and product_id.uom_id.id,
                                                      'company_id': self.env.user.company_id.id
                                                      })
                    process_message = ">>> Inventory Line Created Product Name : {0} and Quantity: {1} ".format(product_id.name, available_qty)
                    _logger.info(process_message)
                    warehouse_id.create_skuvault_operation_detail('product', 'import', data, items_data, operation_id, warehouse_id,False, process_message)
                inventory_id.sudo().action_start()
                inventory_id.sudo().action_validate()
                self.message_post("Inventory Updated : {0}".format(available_qty))
                operation_id.skuvault_message = "Inventory Update Process Completed"
            except Exception as error:
                _logger.info(error)
                warehouse_id.create_skuvault_operation_detail('product', 'import', False, False, operation_id, warehouse_id, True, error)