# -*- coding: utf-8 -*-
{
    'name': "eCommerce Minimum Checkout Amount Limit",

    'summary': """Set minimum checkout price limit""",

    'description': """
       Prevent user to checkout if cart amount is less the required amount.
    """,

    'author': 'ErpMstar Solutions',
    'category': 'eCommerce',
    'version': '1.0',

    # any module necessary for this one to work correctly
    'depends': ['website_sale'],

    # always loaded
    'data': [
        'views/views.xml',
        'views/templates.xml',
    ],

    'assets': {
        'web.assets_frontend': [
            '/website_sale_checkout_limit/static/src/js/category.js',
        ]
    },
    # only loaded in demonstration mode
    'demo': [
    ],
    'installable': True,
    'application': True,
    'images': ['static/description/banner.jpg'],
    'price': 25,
    'currency': 'EUR',
}
