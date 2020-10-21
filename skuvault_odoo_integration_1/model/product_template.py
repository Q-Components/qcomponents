# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
import logging
from odoo import models
import requests
import json

_logger = logging.getLogger(__name__)

class SkuvaultPorductTemplate(models.Model):
    _inherit = 'product.template'


    def skuvault_post_api_request_data(self):
        """
        :return: this method return request data for post api
        """
        selected_products_ids = self._context.get('active_ids')
        product_ids = self.env['product.template'].search([('id', 'in', selected_products_ids)])
        items = []

        for product_id in product_ids:
            data = {
                        "Sku": "TPRD1",   # required
                        "Description": "Test Product By API",
                        "ShortDescription": False,
                        "LongDescription": product_id.description,
                        "Classification": False, #	If provided, classification must exist in SkuVault.
                        "Supplier": False,
                        "Brand": False,
                        "Code": product_id.barcode,
                        "PartNumber": False,
                        "Cost": 0,
                        "SalePrice": product_id.lst_price,
                        "RetailPrice": product_id.standard_price,
                        "Weight": "{}".format(product_id.weight),
                        "WeightUnit": product_id.weight_uom_name,
                        "VariationParentSku": "String",
                        "ReorderPoint": 0,
                        "MinimumOrderQuantity": 0,
                        "MinimumOrderQuantityInfo": "String",
                        "Note": "String",
                        "Statuses": [
                            "String"
                        ],
                        "Pictures": [
                            "String"
                        ],
                        "Attributes": {
                            "Alt Number": "987654321"
                        },
                        "SupplierInfo": [
                            {
                                "SupplierName": "1610",
                                "SupplierPartNumber": "String",
                                "Cost": "String",
                                "LeadTime": "String",
                                "IsActive": "String",
                                "IsPrimary": True
                            }
                        ]
                    }

            items.append(data)
        return items

    def skuvault_update_products(self):
        """
        :return: this method update selected product
        """
        print("Thats Work")
        warehouse_id = self.warehouse_id.search([('use_skuvault_warehouse_management', '=', True)])
        request_data = {
                           "Items": self.skuvault_post_api_request_data(),
                           "TenantToken":warehouse_id and warehouse_id.skuvault_tenantToken,
                           "UserToken": warehouse_id and warehouse_id.skuvault_UserToken
                        }
        try:
            api_url = "%s/api/products/updateProducts"%(warehouse_id.skuvault_api_url)
            response_data = requests.post(url=api_url, data=json.dumps(request_data))
            if response_data.status_code in [200, 201, 202]:
                _logger.info(">>>>>>>>>> get successfully response from {}".format(api_url))
                response_data = response_data.json()
                if response_data.get('Status') == 'Accepted' or response_data.get('Status') == 'OK':
                    _logger.info(">>>>> Successfully product update")
                    return {
                        'effect': {
                            'fadeout': 'slow',
                            'message': 'Successfully products update',
                            'img_url': '/web/static/src/img/smile.svg',
                            'type': 'rainbow_man',
                        }
                    }
                else:
                    raise ValidationError("Get Issue to update product {}".format(response_data.get("Errors")))

            else:
                raise ValidationError("getting some issue {}".format(response_data.text))
        except Exception as error:
            raise ValidationError(error)