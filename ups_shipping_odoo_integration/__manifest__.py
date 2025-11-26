# -*- coding: utf-8 -*-pack
{

    # App information
    'name': 'UPS shipping odoo integration',
    'category': 'Website',
    'version': '19.0.1.0',
    'summary': """At 𝗩𝗿𝗮𝗷𝗮 𝗧𝗲𝗰𝗵𝗻𝗼𝗹𝗼𝗴𝗶𝗲𝘀, we continue to innovate as a globally renowned 𝘀𝗵𝗶𝗽𝗽𝗶𝗻𝗴 𝗶𝗻𝘁𝗲𝗴𝗿𝗮𝘁𝗼𝗿 𝗮𝗻𝗱 𝗢𝗱𝗼𝗼 𝗰𝘂𝘀𝘁𝗼𝗺𝗶𝘇𝗮𝘁𝗶𝗼𝗻 𝗲𝘅𝗽𝗲𝗿𝘁. Our widely accepted shipping connections are made to easily interface with Odoo, simplifying everything from creating labels to tracking shipments—all from a single dashboard. We’re excited to introduce UPS Odoo Connectors your one stop solution for seamless global shipping management, now available on the Odoo App Store! At Vraja Technologies, we continue to be at the forefront of Odoo shipping integrations, ensuring your logistics run smoothly across countries. Users also search using these keywords Vraja Odoo Shipping Integration, Vraja Odoo shipping Connector, Vraja Shipping Integration, Vraja shipping Connector, UPS Odoo Shipping Integration, UPS Odoo shipping Connector, UPS Shipping Integration, UPS shipping Connector, UPS vraja technologies, Odoo UPS.""",
    'license': 'OPL-1',

    # Dependencies
    'depends': ['delivery','stock','stock_delivery','sale_management'],

    # Views
    'data': [
        'security/ir.model.access.csv',
        'data/delivery_ups.xml',
        'data/ir_crone.xml',
        'view/res_company.xml',
        'view/delivery_carrier.xml',
        'view/sale_order.xml',
        'view/stock_picking.xml',
    ],
    # Odoo Store Specific
    'images': ['static/description/cover.gif'],

    # Author
    'author': 'Vraja Technologies',
    'website': 'http://www.vrajatechnologies.com',
    'maintainer': 'Vraja Technologies',

    # Technical
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'live_ups_url': 'https://www.vrajatechnologies.com/contactus',
    'price': '75',
    'currency': 'EUR',

}
# version changelog
#18.0
