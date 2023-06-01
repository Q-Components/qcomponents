# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
import logging
from odoo import models, fields, _
import requests
import json
import time

_logger = logging.getLogger(__name__)

class PorductProduct(models.Model):
    _inherit = 'product.product'

    x_studio_manufacturer = fields.Char(string='manufacturer',related='product_tmpl_id.x_studio_manufacturer',readonly=False)
    x_studio_condition_1 = fields.Char(string='condition',related='product_tmpl_id.x_studio_condition_1',readonly=False)
    x_studio_package = fields.Char(string='Package',related='product_tmpl_id.x_studio_package',readonly=False)

    def update_inventory_from_variant_manually_to_odoo(self):
        warehouse_id = self.env['stock.warehouse'].search([('use_skuvault_warehouse_management', '=', True)])
        if not warehouse_id.skuvault_tenantToken and warehouse_id.skuvault_UserToken:
            raise ValidationError(_("Please generate authentication code"))
        operation_id = self.env['skuvault.operation'].create(
            {'skuvault_operation': 'product', 'skuvault_operation_type': 'import', 'warehouse_id': warehouse_id.id,
             'company_id': self.env.user.company_id.id, 'skuvault_message': 'Processing...'})
        get_inventory_by_location_url = "%s/api/inventory/getInventoryByLocation" % (warehouse_id.skuvault_api_url)
        data = {
            "TenantToken": "{}".format(warehouse_id.skuvault_tenantToken),
            "UserToken": "{}".format(warehouse_id.skuvault_UserToken),
            "ProductSKUs": list(self.mapped('default_code'))
        }
        try:
            _logger.info("{}".format(data))
            response_data = warehouse_id.skuvault_api_calling(get_inventory_by_location_url, data)
            inventory_location_list = response_data.get('Items')
            _logger.info(">> Inventory Location List : {}".format(inventory_location_list))
            for sku, location_datas in inventory_location_list.items():
                location_code = []
                product_template_id = self.env['product.template'].search([('default_code', '=', sku)], limit=1)
                _logger.info(">>>>>>>> {0}".format(product_template_id))
                for location_data in location_datas:
                    location_code.append(location_data.get('LocationCode'))
                    _logger.info(">> Location Code : {}".format(location_code))
                product_template_id.sku_location = ','.join(location_code)
        except Exception as error:
            _logger.info(error)
        try:
            for items_data in self.mapped('default_code'):
                product_tmpl_id = self.env['product.template'].search([('default_code', '=', items_data)], limit=1)
                product_api_url = "%s/api/products/getProduct" % (warehouse_id.skuvault_api_url)
                try:
                    headers = {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    }
                    product_request_data = {
                        "ProductCode": product_tmpl_id.default_code,
                        "TenantToken": "{}".format(warehouse_id.skuvault_tenantToken),
                        "UserToken": "{}".format(warehouse_id.skuvault_UserToken)
                    }
                    response_data = requests.post(url=product_api_url, data=json.dumps(product_request_data),
                                                  headers=headers)
                    if response_data.status_code in [200, 201]:
                        product_response_data = response_data.json()
                        if product_response_data.get('Product'):
                            product_data = product_response_data.get('Product')
                            vals = {
                                'description': product_data.get('Description'),
                                'default_code': product_data.get('Sku'),
                                'name': product_data.get('PartNumber', '') or product_data.get('Sku'),
                                'weight': product_data.get('WeightValue'),
                                'type': 'product',
                                'supplier_name': product_data.get('Supplier'),
                                'standard_price': product_data.get('Cost')}
                            for attribute_data in product_data.get('Attributes'):
                                if attribute_data.get('Name') == 'Category' and attribute_data.get('Value'):
                                    vals.update({'x_studio_category': attribute_data.get('Value')})
                                elif attribute_data.get('Name') == 'Alt Manufacturer' and attribute_data.get('Value'):
                                    brand_id = self.env['bc.product.brand'].search(
                                        [('name', '=', attribute_data.get('Value'))])
                                    if not brand_id:
                                        brand_id = self.env['bc.product.brand'].create(
                                            {'name': attribute_data.get('Value')})
                                    vals.update({'x_studio_manufacturer': brand_id.id})
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

                            product_tmpl_id.write(vals)
                            _logger.info("Product Vals : {}".format(vals))
                            product_id = self.env['product.product'].search(
                                [('product_tmpl_id', '=', product_tmpl_id.id)], limit=1)
                            _logger.info("Product >>>>>>>>> {0}{1}".format(product_tmpl_id, product_id))
                            quant_ids = self.env['stock.quant'].sudo().search(
                                [('product_id', '=', product_id.id), ('location_id', '!=', 8),
                                 ('location_id.usage', '=', 'internal')])
                            if quant_ids:
                                quant_ids.sudo().unlink()
                            inventory_id = self.env['stock.quant'].sudo().search(
                                [('product_id', '=', product_id.id), ('location_id.usage', '=', 'internal')])
                            available_qty = product_data.get('QuantityOnHand')
                            if not inventory_id:
                                inventory_vals = {
                                    'product_id': product_id.id,
                                    'location_id': warehouse_id.lot_stock_id.id,
                                    'inventory_date': time.strftime("%Y-%m-%d %H:%M:%S"),
                                    'company_id': warehouse_id.company_id.id,
                                    'inventory_quantity': available_qty
                                }
                                inventory_id = self.env['stock.quant'].sudo().create(inventory_vals)
                                _logger.info("Inventory Created : {}".format(inventory_id))
                            else:
                                inventory_id.inventory_quantity = available_qty
                        else:
                            process_message = ">>>>> get some error from{}".format(response_data.text)
                            _logger.info(process_message)
                            warehouse_id.sudo().create_skuvault_operation_detail('product', 'import', False, False,
                                                                                 operation_id, self, False,
                                                                                 process_message)
                except Exception as error:
                    _logger.info(error)
                    process_message = "{}".format(error)
                    warehouse_id.sudo().create_skuvault_operation_detail('product', 'import', False, False,
                                                                         operation_id, self, False, process_message)
                inventory_id.sudo().action_apply_inventory()
                operation_id.skuvault_message = "Inventory Update Process Completed"
        except Exception as error:
            _logger.info(error)
            warehouse_id.create_skuvault_operation_detail('product', 'import', False, False, operation_id, warehouse_id,
                                                          True, error)
