# -*- coding: utf-8 -*-

{
    "name": "Website Customisation",
    "version": "1.0",
    "category": "Website",
    'summary': 'Website Customisation',
    "description": """
        Website Customisation
    """,
    "author": "WebRulers Infotech",
    "website": "http://webrulersinfotech.com",
    "depends": ['base', 'website_sale', 'stock'],
    "data": [
        'data/data.xml',
        'views/templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'wr_website_customisation/static/src/js/quick_shop.js',
            'wr_website_customisation/static/src/xml/quick_shop.xml',
        ],
    },
    "auto_install": False,
    "installable": True,
    "license": "LGPL-3",
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
