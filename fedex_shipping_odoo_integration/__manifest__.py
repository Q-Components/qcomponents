# -*- coding: utf-8 -*-pack
{

    # App information
    'name': 'FedEx Odoo Shipping Integration',
    'category': 'Website',
    'version': '19.0.1.3',
    'summary': """At 𝗩𝗿𝗮𝗷𝗮 𝗧𝗲𝗰𝗵𝗻𝗼𝗹𝗼𝗴𝗶𝗲𝘀, we continue to innovate as a globally renowned 𝘀𝗵𝗶𝗽𝗽𝗶𝗻𝗴 𝗶𝗻𝘁𝗲𝗴𝗿𝗮𝘁𝗼𝗿 𝗮𝗻𝗱 𝗢𝗱𝗼𝗼 𝗰𝘂𝘀𝘁𝗼𝗺𝗶𝘇𝗮𝘁𝗶𝗼𝗻 𝗲𝘅𝗽𝗲𝗿𝘁. Our widely accepted shipping connections are made to easily interface with Odoo, simplifying everything from creating labels to tracking shipments—all from a single dashboard. We’re excited to introduce FedEx Odoo Connectors your one stop solution for seamless global shipping management, now available on the Odoo App Store! At Vraja Technologies, we continue to be at the forefront of Odoo shipping integrations, ensuring your logistics run smoothly across countries. Users also search using these keywords Vraja Odoo Shipping Integration, Vraja Odoo shipping Connector, Vraja Shipping Integration, Vraja shipping Connector, FedEx Odoo Shipping Integration, FedEx Odoo shipping Connector, FedEx Shipping Integration, FedEx shipping Connector, FedEx vraja technologies, Odoo FedEx.""",
    'description': """ """,

    # Dependencies
    'depends': ['delivery','stock','stock_delivery'],

   # Views
      'data': [
            'data/ir_cron.xml',
            'data/delivery_fedex.xml',
            'views/res_company.xml',
            'views/delivery_carrier_view.xml',
            'views/sale_view.xml',
            'views/stock_picking_vts.xml'
            ],

    # Author

    'author': 'Vraja Technologies',
    'website': 'https://www.vrajatechnologies.com',
    'maintainer': 'Vraja Technologies',
    'live_test_url': 'https://www.vrajatechnologies.com/contactus',
    'images': ['static/description/cover.gif'],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': '111',
    'currency': 'EUR',
    'license': 'OPL-1',

}
# 1.0.1 - update order.tax_total.get('amount_total to order.amount_total')
#18.0.1.2 manage commerecial label response
#18.0.1.3 change accoun number view from company level to shipping method level
