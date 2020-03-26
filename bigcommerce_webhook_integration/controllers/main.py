# -*- coding: utf-8 -*-
import json
import time
import logging
from odoo import http
from odoo.exceptions import ValidationError
from datetime import datetime
from requests import request
#from odoo.http import request
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
            _logger.warning('>>>>>>>>>>>>>>> \n \n \n  Product Response >>>>>>>%s' % (response))
            location_id = bigcommerce_store_id.warehouse_id.lot_stock_id
            product_template_id = http.request.env['product.template'].search([('bigcommerce_product_id','=',response.get('data').get('id'))],limit=1)
            _logger.warning('>>>>>>>>>>>>>>> \n \n Product Template >>>>>>>%s' % (product_template_id))
            if not product_template_id:                
                status, product_template_id = http.request.env['product.template'].create_product_template(response.get('data'),bigcommerce_store_id)
                _logger.info("Status : {0} Product Template : {1}".format(status,product_template_id))
                if product_template_id:
                    quant_id = http.request.env['stock.quant'].with_user(1).search([('product_tmpl_id','=',product_template_id.id),('location_id','=',location_id.id)],limit=1)
                    if not quant_id:
                        vals = {'product_tmpl_id':product_template_id.id,'location_id':location_id.id,'inventory_quantity':response.get('data').get('inventory_level'),'product_id':product_template_id.product_variant_id.id,'quantity':response.get('data').get('inventory_level')}
                        http.request.env['stock.quant'].with_user(1).create(vals)
                    else:
                        quant_id.with_user(1).write({'inventory_quantity':response.get('data').get('inventory_level'),'quantity':response.get('data').get('inventory_level')})
                    _logger.info("Product Inventory : {}".format(quant_id.quantity))
                if status != True:
                    product_process_message = "%s : Product is not imported Yet! %s" % (response.get('id'), product_template_id)
                    _logger.info("Getting an Error In Import Product Response {}".format(product_process_message))
        except Exception as e:
            product_process_message = "%s : Product is not imported Yet! %s" % (response.get('id'),e)
            _logger.info("Getting an Error In Import Product Responase {}".format(product_process_message))
        
    @http.route('/store/order/statusUpdated', type='json', auth="none", methods=['POST'])
    def update_bigcommerce_order_status(self, **kw):
        _logger.warning('>>>>>>>>>>>>>>> \n \n \n Final data >>>>>>>%s' % (http.request.httprequest.data))
        status_update_dict = http.request.httprequest.data.decode("utf-8")
        inventory_data = json.loads(status_update_dict)
        bigcommerce_order_id = inventory_data.get('data').get('id')
        sale_order_id = http.request.env['sale.order'].with_user(1).search([('big_commerce_order_id','=',bigcommerce_order_id)])
        _logger.warning('>>>>>>>>>>>>>>> Sale Order  >>>>>>>>> {}'.format(sale_order_id))
        if sale_order_id:
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
                        product_template_id = http.request.env['product.template'].with_user(1).search(
                            [('bigcommerce_product_id', '=', bigcommerce_product_id)])
                        if response.get('product_options'):
                            for product_option in response.get('product_options'):
                                attribute_obj = http.request.env['product.attribute'].with_user(1).search(
                                    [('bigcommerce_attribute_id', '=', product_option.get('product_option_id'))])
                                value_obj = http.request.env['product.attribute.value'].with_user(1).search(
                                    [('bigcommerce_value_id', '=', int(product_option.get('value')))])
                                # attrib.append(attribute_obj.id)
                                # val_obj.append(value_obj.id)
                                template_attribute_obj = http.request.env['product.template.attribute.value'].with_user(1).search(
                                    [('attribute_id', 'in', attribute_obj.ids),
                                     ('product_attribute_value_id', 'in', value_obj.ids),
                                     ('product_tmpl_id', '=', product_template_id.id)])
                                # val_obj.append(template_attribute_obj)
                                domain = [('product_template_attribute_value_ids', 'in', template_attribute_obj.ids),
                                          ('product_tmpl_id', '=', product_template_id.id)]
                                if product_ids:
                                    domain += [('id', 'in', product_ids)]
                                product_id = http.request.env['product.product'].with_user(1).search(domain)
                                product_ids += product_id.ids
                        else:
                            product_id = product_template_id.product_variant_id
                        order_line = http.request.env['sale.order.line'].with_user(1).search([('product_id','=',product_id.id),('order_id','=',sale_order_id.id)],limit=1)
                        if order_line:
                            order_line.quantity_shipped = response.get('quantity_shipped')
                    sale_order_id.with_user(1).auto_process_delivery_order(sale_order_id.picking_ids)
                else:
                    _logger.warning("Order Should Be Shipped, Partially Shipped, Completed !")
            except Exception as e:
                _logger.warning(e)


#     @http.route('/store/sku/inventory/updated', type='json', auth="none", methods=['POST'])
#     def update_store_sku_inventory__webhook(self, **kw):
#         status_update_dict = http.request.httprequest.data.decode("utf-8")
#         inventory_data = json.loads(status_update_dict)
#         _logger.info("Get Successfull Response {}".format(inventory_data))
#         method = inventory_data.get('data').get('inventory').get('method')
#         values = inventory_data.get('data').get('inventory').get('value')
#         variant_id = inventory_data.get('data').get('inventory').get('variant_id')
#         product_id = inventory_data.get('data').get('inventory').get('product_id')
#         store_hash = inventory_data.get('hash')
#         bigcommerce_store_id = http.request.env['bigcommerce.store.configuration'].seacrh([('bigcommerce_store_hash','=',store_hash)])
#         warehouse_id = bigcommerce_store_id.warehouse_id
#         if method == "absolute":
#             inventroy_line_obj = http.request.env['stock.inventory.line']
#             inventory_name = "BigCommerce_Inventory_%s" % (str(datetime.now().date()))
#             inventory_vals = {
#                 'name': inventory_name,
#                 'location_ids': [(6, 0, warehouse_id.lot_stock_id.ids)],
#                 'date': time.strftime("%Y-%m-%d %H:%M:%S"),
#                 'company_id': warehouse_id.company_id and warehouse_id.company_id.id or False,
#                 'filter': 'partial'
#             }
#             self.create(inventory_vals)
#             _logger.info("Successfull Create Inventory")
#             product_product = http.request.env['product.product']
#             variant = product_product.sudo().search([('bigcommerce_product_variant_id','=',variant_id )])
#             if variant:
#                 variant.qty_available = values
#                 request.env.cr.commit()
#                 _logger.info("Successfully Product Qty Update By Variant Id")
#             else:
#                 product = product_product.sudo().search([('bigcommerce_product_id','=',product_id )])
#                 if product:
#                     product.qty_available = values
#                     request.env.cr.commit()
#                     _logger.info("Successfully Product Qty Update By Product Id")
#                 else:
#                     _logger.info("Product Not Found !!!")
#         else:
#             _logger.info("Not Absolute Method")

    @http.route('/store/product/inventory/updated', type='json', auth="none", methods=['POST'])
    def update_store_product_inventory_webhook(self, **kw):
        status_update_dict = http.request.httprequest.data.decode("utf-8")
        inventory_data = json.loads(status_update_dict)
        _logger.info("Get Successfull Response {}".format(inventory_data))
        method = inventory_data.get('data').get('inventory').get('method')
        product_qty = inventory_data.get('data').get('inventory').get('value')
        product = inventory_data.get('data').get('inventory').get('product_id')

        store = inventory_data.get('producer').replace("stores/","")
        bigcommerce_store_id = http.request.env['bigcommerce.store.configuration'].sudo().search([('bigcommerce_store_hash','=',store)])

        warehouse_id = bigcommerce_store_id.warehouse_id
        if method == "absolute":
            inventroy_line_obj = http.request.env['stock.inventory.line']
            inventory_name = "BigCommerce_Inventory_%s" % (str(datetime.now().date()))
            inventory_vals = {
                'name': inventory_name,
                'location_ids': [(6, 0, warehouse_id.sudo().lot_stock_id.ids)],
                'accounting_date': time.strftime("%Y-%m-%d %H:%M:%S"),
                'date': time.strftime("%Y-%m-%d %H:%M:%S"),
                'company_id': warehouse_id.company_id and warehouse_id.company_id.id or False}

            inventory_id = http.request.env['stock.inventory'].sudo().create(inventory_vals)
            _logger.info("Successfull Create Inventory")
            product_product = http.request.env['product.product']
            product_id = product_product.sudo().search([('bigcommerce_product_id', '=', product)])
            if product_id:
                inventroy_line_obj.sudo().create({'product_id': product_id.id,
                                                            'inventory_id': inventory_id and inventory_id.sudo().id,
                                                            'location_id': warehouse_id.sudo().lot_stock_id.id,
                                                            'product_qty': product_qty,
                                                            'product_uom_id': product_id.uom_id and product_id.uom_id.id,
                                                            })
                _logger.info("Successfully Product Qty Update By Product Id")
            else:
                _logger.info("Product Not Found !!!")
            
            http.request.env.cr.commit()
            _logger.info("Inventory Action Start... !!!")
            inventory_id.with_user(1).action_start()
            _logger.info("Inventory Action Start Done And Continue Validate... !!!")
            inventory_id.with_user(1).action_validate()
            _logger.info("Inventory Action Validate Method Done... !!!")
        else:
            _logger.info("Not Absolute Method")

