# -*- coding: utf-8 -*-
{
    'name': 'Shippypro Shipping Integration',
    'category': 'Website',
    'author': "Vraja Technologies",
    'version': '15.0.27.10.2021',
    'summary': """""",
    'description': """Using Shippypro odoo Integration We export order to shippypro..and generate label in odoo and get tracking information.we also providing following modules Shipping Operations, shipping, odoo shipping integration,
    odoo shipping connector, dhl express, fedex, ups, gls, usps, stamps.com, shipstation, bigcommerce, easyship, 
    amazon shipping, sendclound, ebay, shopify.""",
    'depends': ['delivery'],
    'data': ['security/ir.model.access.csv',
             'views/res_company.xml',
             'views/delivery_carrier.xml',
             'views/sale_order.xml',
             'views/stock_picking.xml'],
    'maintainer': 'Vraja Technologies',
    'website': 'https://www.vrajatechnologies.com',
    'images': ['static/description/cover.jpg'],
    'demo': [],
    'installable': True,
    'live_test_url': 'https://www.vrajatechnologies.com/contactus',
    'application': True,
    'auto_install': False,
    'price': '249',
    'currency': 'EUR',
    'license': 'OPL-1',
}

# version changelog
# 14.0.30.03.2021 fix authentication issue , fix set service issue
# 14.0.04.10.2021 latest version
# 14.0.18.10.2021 Create Shipment without Rate API
# 15.0.27.10.2021 fix import carrier bug