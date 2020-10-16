# -*- coding: utf-8 -*-
{
    'name': 'SKUVAULT Integration',
    'category': 'Website',
    'author': "Vraja Technologies",
    'version': '13.0',
    'summary': """ """,
    'description': """""",
    'depends': ['delivery', 'import_inventory'],
    'data': [
            'view/stock_warehouse.xml',
            'view/product_template.xml',
            'data/skuvault_inventory_crone.xml',
            'data/skuvault_import_product_crone.xml'
            #  'views/sale_order.xml',
            #  'views/product_template.xml',
            #  'views/stock_picking.xml',

             ],
    'images': [''],
    'maintainer': 'Vraja Technologies',
    'website':'www.vrajatechnologies.com',
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'currency': 'EUR',
    'license': 'OPL-1',
}
