# -*- coding: utf-8 -*-
{
    'name': 'Email Configuration For Outlook',
    'version': '16.0.1.0.0',
    'summary': '''Email Configuration For Outlook is  Effortlessly sync your emails between Odoo and Outlook,
     ensuring all your communications are centralized and up to date across both platforms. This module simplifies
      the setup of incoming and outgoing mail servers by automatically configuring them directly from your preferences.
    ''',
    'description': """
        Email Configuration for Outlook is designed to streamline and enhance your email management within the Odoo platform. 
        This module offers a range of features that optimize email communication, boost productivity, and provide seamless
         integration with Outlook mail server. Thus, Advanced Email Configuration for Outlook Odoo Module, allows to optimize
          your email management, enhance communication, and boost productivity within the Odoo ecosystem while leveraging the
           familiar interface and features of Outlook.
    """,
    'category': 'Discuss',
    "author": "Silent Infotech Pvt. Ltd.",
    'website': 'https://silentinfotech.com',
    'price': 35,
    'currency': 'USD',
    'depends': ['advanced_email_configurator', 'microsoft_outlook','advance_email_configurator_base'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_users_views.xml',
        'data/default_data.xml',
    ],
    "images": ['static/description/banner.gif'],

    'qweb': [
    ],
    'application': True,
    'license': u'OPL-1',
    'auto_install': False,
    'installable': True,
    'live_test_url': '',
    'assets': {
        'web.assets_backend': [
            'email_configuration_for_outlook_sit/static/src/js/systray.js',
            'email_configuration_for_outlook_sit/static/src/xml/systray.xml',
        ]
    }
}
