# -*- coding: utf-8 -*-
import json
import time
import logging
from odoo import http
from odoo.exceptions import ValidationError
from datetime import datetime
from requests import request
_logger = logging.getLogger(__name__)


class WebHook(http.Controller):

    @http.route('/store/product/inventory/order/updated', type='json', auth="none", methods=['POST'])
    def update_bigcommerce_quantity_webhook(self, **kw):
        _logger.warning('>>>>>>>>>>>>>>> \n \n \n Final data >>>>>>>%s' % (http.request.httprequest.data))
        inventory_data_dict = http.request.httprequest.data
        inventory_product_dict = inventory_data_dict.get('data')
        _logger.warning('>>>>>>>>>>>>>>> \n \n \n Final data >>>>>>>%s' % (inventory_product_dict))
    
    
    @http.route('/store/product/created', type='json', auth="none", methods=['POST'])
    def create_product_using_webhook(self, **kw):
        _logger.warning('>>>>>>>>>>>>>>> \n \n \n Final data >>>>>>>%s' % (http.request.httprequest.data))
        create_product_dict = http.request.httprequest.data.decode("utf-8")
        product_data = json.loads(create_product_dict)
        store = product_data.get('producer').replace("stores/","")
        bigcommerce_store_id = http.request.env['bigcommerce.store.configuration'].sudo().search([('bigcommerce_store_hash','=',store)])
        bigcommerce_store_hash = bigcommerce_store_id.bigcommerce_store_hash
        bigcommerce_client_seceret = bigcommerce_store_id.bigcommerce_x_auth_client
        bigcommerce_x_auth_token = bigcommerce_store_id.bigcommerce_x_auth_token
        headers = {"Accept": "application/json",
                   "X-Auth-Client": "{}".format(bigcommerce_client_seceret),
                   "X-Auth-Token": "{}".format(bigcommerce_x_auth_token),
                   "Content-Type": "application/json"}

        api_url = "%s%s/v3/catalog/products/%s" % (bigcommerce_store_id.bigcommerce_api_url, bigcommerce_store_hash, product_data.get('data').get('id'))
        try:
            response = request(method="GET", url=api_url, headers=headers)
            response = response.json()
            product_template_id = http.request.env['product.template'].search([('bigcommerce_product_id','=',response.get('id'))],limit=1)
            if not product_template_id:
                status, product_template_id = http.request.env['product.template'].create_product_template(response,bigcommerce_store_id)
                product_process_message = "%s : Product is not imported Yet! %s" % (response.get('id'), product_template_id)
                _logger.info("Getting an Error In Import Product Responase".format(product_template_id))
        except Exception as e:
            product_process_message = "%s : Product is not imported Yet! %s" % (response.get('id'),e)
            _logger.info("Getting an Error In Import Product Responase".format(e))
        
    @http.route('/store/order/statusUpdated', type='json', auth="none", methods=['POST'])
    def update_bigcommerce_order_status(self, **kw):
        _logger.warning('>>>>>>>>>>>>>>> \n \n \n Final data >>>>>>>%s' % (http.request.httprequest.data))
        status_update_dict = http.request.httprequest.data.decode("utf-8")
        inventory_data = json.loads(status_update_dict)
        store = inventory_data.get('producer').replace("stores/","")
        bigcommerce_store_id = http.request.env['bigcommerce.store.configuration'].sudo().search([('bigcommerce_store_hash','=',store)])
        bigcommerce_store_hash = bigcommerce_store_id.bigcommerce_store_hash
        bigcommerce_client_seceret = bigcommerce_store_id.bigcommerce_x_auth_client
        bigcommerce_x_auth_token = bigcommerce_store_id.bigcommerce_x_auth_token
        headers = {"Accept": "application/json",
                   "X-Auth-Client": "{}".format(bigcommerce_client_seceret),
                   "X-Auth-Token": "{}".format(bigcommerce_x_auth_token),
                   "Content-Type": "application/json"}

        _logger.warning('>>>>>>>>>>>>>>> \n \n \n Final data >>>>>>>%s' % (inventory_data))
        url = "%s%s/v2/orders/%s/products" % (
        bigcommerce_store_id.bigcommerce_api_url, bigcommerce_store_hash, inventory_data.get('data') and inventory_data.get('data').get('id'))
        try:
            response = request(method="GET", url=url, headers=headers)
            response = response.json()
            _logger.warning('Get Product Shipped QTY %s' % (response))
            if inventory_data.get('data') and inventory_data.get('data').get('status') and inventory_data.get('data').get('status').get('new_status_id') in [2,3,10]:
                for response in response:
                    product_ids = []
                    domain = []
                    bigcommerce_product_id = response.get('product_id')
                    product_template_id = http.request.env['product.template'].sudo().search(
                        [('bigcommerce_product_id', '=', bigcommerce_product_id)])
                    if response.get('product_options'):
                        for product_option in response.get('product_options'):
                            attribute_obj = http.request.env['product.attribute'].sudo().search(
                                [('bigcommerce_attribute_id', '=', product_option.get('product_option_id'))])
                            value_obj = http.request.env['product.attribute.value'].sudo().search(
                                [('bigcommerce_value_id', '=', int(product_option.get('value')))])
                            # attrib.append(attribute_obj.id)
                            # val_obj.append(value_obj.id)
                            template_attribute_obj = http.request.env['product.template.attribute.value'].sudo().search(
                                [('attribute_id', 'in', attribute_obj.ids),
                                 ('product_attribute_value_id', 'in', value_obj.ids),
                                 ('product_tmpl_id', '=', product_template_id.id)])
                            # val_obj.append(template_attribute_obj)
                            domain = [('product_template_attribute_value_ids', 'in', template_attribute_obj.ids),
                                      ('product_tmpl_id', '=', product_template_id.id)]
                            if product_ids:
                                domain += [('id', 'in', product_ids)]
                            product_id = http.request.env['product.product'].sudo().search(domain)
                            product_ids += product_id.ids
                    else:
                        product_id = product_template_id.product_variant_id
                    order_line = http.request.env['sale.order.line'].sudo().search([('product_id','=',product_id.id)],limit=1)
                    if order_line:
                        order_line.quantity_shipped = response.get('quantity_shipped')
                    request.env.cr.commit()
            else:
                raise ValidationError("Order Should Be Shipped, Partially Shipped, Completed !")
        except Exception as e:
            raise ValidationError(e)


    @http.route('/store/sku/inventory/updated', type='json', auth="none", methods=['POST'])
    def update_store_sku_inventory__webhook(self, **kw):
        status_update_dict = http.request.httprequest.data.decode("utf-8")
        inventory_data = json.loads(status_update_dict)
        _logger.info("Get Successfull Response {}".format(inventory_data))
        method = inventory_data.get('data').get('inventory').get('method')
        values = inventory_data.get('data').get('inventory').get('value')
        variant_id = inventory_data.get('data').get('inventory').get('variant_id')
        product_id = inventory_data.get('data').get('inventory').get('product_id')
        store_hash = inventory_data.get('hash')
        bigcommerce_store_id = http.request.env['bigcommerce.store.configuration'].seacrh([('bigcommerce_store_hash','=',store_hash)])
        warehouse_id = bigcommerce_store_id.warehouse_id
        if method == "absolute":
            inventroy_line_obj = http.request.env['stock.inventory.line']
            inventory_name = "BigCommerce_Inventory_%s" % (str(datetime.now().date()))
            inventory_vals = {
                'name': inventory_name,
                'is_inventory_report': True,
                'location_ids': [(6, 0, warehouse_id.lot_stock_id.ids)],
                'date': time.strftime("%Y-%m-%d %H:%M:%S"),
                'company_id': warehouse_id.company_id and warehouse_id.company_id.id or False,
                'filter': 'partial'
            }
            self.create(inventory_vals)
            _logger.info("Successfull Create Inventory")
            product_product = http.request.env['product.product']
            variant = product_product.sudo().search([('bigcommerce_product_variant_id','=',variant_id )])
            if variant:
                variant.qty_available = values
                request.env.cr.commit()
                _logger.info("Successfully Product Qty Update By Variant Id")
            else:
                product = product_product.sudo().search([('bigcommerce_product_id','=',product_id )])
                if product:
                    product.qty_available = values
                    request.env.cr.commit()
                    _logger.info("Successfully Product Qty Update By Product Id")
                else:
                    _logger.info("Product Not Found !!!")
        else:
            _logger.info("Not Absolute Method")
