# -*- coding: utf-8 -*-pack
{

    # App information
    'name': 'UPS Shipping Odoo Integration',
    'category': 'Website',
    'version': '13.17.12.21',
    'summary': """ """,
    'description': """
    	UPS Integration helps you integrate & manage your ups account in odoo. manage your Delivery/shipping operations directly from odoo.
	Export Order To ups On Validate Delivery Order.
        Auto Import Tracking Detail From ups to odoo.
        Generate Label in Odoo..
        We also Provide the dhl,bigcommerce,shiphero,gls,fedex,usps,easyship,stamp.com,dpd,shipstation,manifest report
""",

    # Dependencies
    'depends': ['delivery'],

    # Views
    'data': [
        'security/ir.model.access.csv',
        'data/delivery_ups.xml',
        'wizard/choose_delivery_package.xml',
        'views/sale_order.xml',
        'views/delivery_carrier_view.xml',
        'views/res_company.xml',
        'views/stock_picking.xml',
        'views/stock_quant_package.xml'
    ],

    # Author

    'author': 'Vraja Technologies',
    'website': 'https://www.vrajatechnologies.com',
    'maintainer': 'Vraja Technologies',
    'live_test_url': 'https://www.vrajatechnologies.com/contactus',
    'images': ['static/description/ups.jpg'],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': '99',
    'currency': 'EUR',
    'license': 'OPL-1',

}

# 14.29.10.21 Latest version
# justin custom changes
# add cod feature for justin
# 13.30.11.21 move third party delivery level to sale level
# 13.14.12.21 third party freight
# 13.15.12.21 fix third party issue
# 13.17.12.21 add street2 field in label
