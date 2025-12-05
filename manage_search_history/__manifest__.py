# -*- coding: utf-8 -*-pack
{
    # App information
    'name': 'Manage Backend Search History For Odoo',
    'category': 'Tools',
    'version': '19.0.1.0',
    'summary': """Using Test Easily manage Shipping Operation in odoo.Export Order While Validate Delivery Order.Import Tracking From Test to odoo.Generate Label in odoo.We also Provide the ups,fedex,dhl express shipping integration.""",
    'license': 'OPL-1',

    # Dependencies
    'depends': ['base', 'web'],

    # Views
    'data': [
        "security/ir.model.access.csv",
        "data/data.xml",
        "views/filter_search_history.xml"
    ],
    # Odoo Store Specific
    'images': ['static/description/cover.gif'],

    # Author
    'author': 'Vraja Technologies',
    'website': 'http://www.vrajatechnologies.com',
    'maintainer': 'Vraja Technologies',
    'assets': {
        'web.assets_backend': [
            '/manage_search_history/static/src/scss/searchbar.scss',
            '/manage_search_history/static/src/js/SearchModel.js',
            '/manage_search_history/static/src/js/searchModel.xml'
        ]
    },

    # Technical
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'live_test_url': 'https://www.vrajatechnologies.com/contactus',
    'price': '199',
    'currency': 'EUR',

}
# version changelog
