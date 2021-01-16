# -*- coding: utf-8 -*-
{
    'name': 'SKUVAULT Integration',
    'category': 'Website',
    'author': "Vraja Technologies",
    'version': '13.0.16.01.2020',
    'summary': """ """,
    'description': """""",
    'depends': ['delivery', 'import_inventory'],
    'data': [
        'security/ir.model.access.csv',
        'view/sale_order.xml',
        'view/stock_warehouse.xml',
        'view/skuvault_operation_details.xml',
        'view/product_template.xml',
        'data/skuvault_inventory_crone.xml',
        'data/skuvault_import_product_crone.xml'
        #  'views/sale_order.xml',
        #  'views/product_template.xml',
        #  'views/stock_picking.xml',

    ],
    'images': [''],
    'maintainer': 'Vraja Technologies',
    'website': 'www.vrajatechnologies.com',
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'currency': 'EUR',
    'license': 'OPL-1',
}
# version changelog
# 13.0.13.01.2020 add export order features
# 13.0.16.01.2020 changes in update quantity
