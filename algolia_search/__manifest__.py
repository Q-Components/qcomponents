# -*- coding: utf-8 -*-
{
    'name': "Algolia Search",

    'summary': """
        Provides autocomplete functionalities using algolia api""",

    'description': """
        Provides autocomplete functionalities using algolia api.
        It also allowed to search on custom fields of product
    """,
    'version': '1.7',
    'category': 'Website/Website',
    'license': 'OPL-1',
    'author': 'Aardvark',
    'website': 'https://www.shopaardvark.com/',
    'support': 'john.wright@shopaardvark.com',

    'depends': ['website', 'website_sale', 'product', 'super_ecom_multi_website_selection'],

    'data': [
        'data/ir_cron.xml',
        'security/ir.model.access.csv',
        'views/algoliaaearchapp.xml',
        'views/templates.xml',
    ],

    'installable': True,
    'application': True,
}
