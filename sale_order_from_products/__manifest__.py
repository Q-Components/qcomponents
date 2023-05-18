# -*- coding: utf-8 -*-
{
    "name": "Create Sale Order from Products",
    "version": "16.00.08.05.2023",
    "category": "Sale",
    "summary": '',
    "license": '',
    "description": """
    - From products create sale order.
    """,
    "author": "Vraja Technologies",
    "depends": ['sale',],
    "data": [
        'security/ir.model.access.csv',
        'wizard/create_order_from_products.xml',
    ],
    'images': [],
    'website': 'https://www.vrajatechnologies.com',
    'live_test_url': 'https://www.vrajatechnologies.com/contactus',
    "auto_install": False,
    "installable": True,
    "application": True,
}
