# -*- coding: utf-8 -*-
{
    'name': 'Odoo Advance Email Configurator Base',
    'version': '16.0.1.0.0',
    'license': 'LGPL-3',
    'summary': 'advance email configrator base',
    'description': """
         This module will help user to choose authentication options in your profiles.
""",
    'author': 'Silent Infotech Pvt. Ltd.',
    'website': 'https://silentinfotech.com',
    'price': 0,
    'currency': 'USD',
    'depends': ['base','mail','advanced_email_configurator'],
    'data': [
        'views/res_users_views.xml',
    ],
}
