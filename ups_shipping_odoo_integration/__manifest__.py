# -*- coding: utf-8 -*-pack
{

    # App information
    'name': 'UPS shipping odoo integration',
    'category': 'Website',
    'version': '16.0.1',
    'summary': """Using ups easily manage Shipping Operation in odoo.Export Order While Validate Delivery Order.Import Tracking From ups to odoo.Generate Label in odoo.We also Provide the ups,fedex,dhl express shipping integration.""",
    'license': 'OPL-1',

    # Dependencies
    'depends': ['delivery'],

    # Views
    'data': [
        'security/ir.model.access.csv',
        'data/delivery_ups.xml',
        'data/ir_crone.xml',
        'view/res_company.xml',
        'view/delivery_carrier.xml',
        'view/sale_order.xml',
        'view/stock_picking.xml',
        'view/stock_quant_package.xml',
    ],
    # Odoo Store Specific
    'images': ['static/description/cover.jpg'],

    # Author
    'author': 'Vraja Technologies',
    'website': 'http://www.vrajatechnologies.com',
    'maintainer': 'Vraja Technologies',

    # Technical
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'live_test_url': 'https://www.vrajatechnologies.com/contactus',
    'price': '99',
    'currency': 'EUR',

}
# version changelog
# 19.02.2024 = add insure functionality in package level
