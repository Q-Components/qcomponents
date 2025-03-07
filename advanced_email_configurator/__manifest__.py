# -*- coding: utf-8 -*-
{
    'name': 'Odoo Advance Email Configurator',
    'summary': 'This module will help user to configure outgoing and incoming mail server.',
    'description': """
        This module will help user to configure outgoing and incoming mail server without any smtp and imap configuration information.
    """,
    'live_test_url': 'https://silentinfotech.com/blog/odoo-advance-email-configurator/',
    'author': 'Silent Infotech Pvt. Ltd.',
    'category': 'Discuss',
    'license': u'OPL-1',
    'price': 159.00,
    'currency': 'USD',
    'website': 'https://silentinfotech.com',
    'version': '16.0.1.0.0',
    'application': True,
    'installable': True,
    'auto_install': False,
    'depends': [
        'base',
        'mail',
        'hr'
    ],
    'external_dependencies': {
        'python': [],
        'bin': [],
    },
    'init_xml': [],
    'update_xml': [],
    'css': [],
    'demo_xml': [],
    'test': [],
    'data': [
        'security/ir.model.access.csv',
        'views/res_users_views.xml',
        'views/mail_server_view.xml',
        'views/res_config_settings_views.xml',
        'views/fetchmail_view.xml',
        'data/default_data.xml',
    ],
    'images': ['static/description/banner.gif'],

    'assets': {
        'web.assets_backend': [
            'advanced_email_configurator/static/src/js/systray.js',
            'advanced_email_configurator/static/src/js/user_menu.js',
            'advanced_email_configurator/static/src/xml/systray.xml',
        ]
    }
}