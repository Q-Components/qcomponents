# -*- coding: utf-8 -*-
{
    'name': "GeoPortal Access Control",

    'summary': "Restrict website access based on user location (country or region).",

    'description': """
GeoPortal Access Control is an Odoo module designed to manage and restrict website access based on the user's geographical location. 
It allows administrators to configure specific countries and regions where the website will be inaccessible, ensuring compliance 
with regional regulations, licensing restrictions, or company policies. The module automatically detects a visitor's location 
and displays customizable warning messages for users in restricted areas, enhancing security and user experience.
    """,
    'author': "Business Dev Hub",
    'maintainer': "Business Dev Hub",
    "support": "business.dev.hub@gmail.com",
    'website': "",

    'category': 'Website',
    'version': '19.0.1.0.0',

    'license': 'OPL-1',
    'price': '20.00',
    'currency': 'USD',

    # Dependencies for proper functionality
    'depends': ['website'],

    # Data files for views and templates
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/blocked_ip_views.xml',
        'views/templates/website_layout.xml',
        'views/website_visitor_views.xml'
    ],

    # Frontend assets (JavaScript, CSS)
    'assets': {
        'web.assets_frontend': [
            'geoportal_access_control/static/src/js/location_checker.js',
        ],
    },
    'images': ['static/description/location_restriction.gif'],
    'installable': True,
    'application': True,
}
