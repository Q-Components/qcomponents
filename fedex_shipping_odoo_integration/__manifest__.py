# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    # App information

    'name': 'Fedex Odoo Shipping Connector',
    'version': '12.0',
    'category': 'Website',
    'summary': 'Connect, Integrate & Manage your FedEx Shipping Operations from Odoo',
    'license': 'OPL-1',

    # Dependencies

    'depends': ['delivery'],

    # Views
    'data': [
            'data/delivery_fedex.xml',
            'views/res_company.xml',
            'views/delivery_carrier_view.xml',
            'views/stock_picking_vts.xml',
            'security/ir.model.access.csv',
            'views/sale_view.xml',
            ],

    # Odoo Store Specific

    'images': ['static/description/FedEx.jpg'],

    # Author

    'author': 'Vraja Technologies',
    'website': '',
    'maintainer': '',

    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': '199' ,
    'currency': 'EUR',

}
