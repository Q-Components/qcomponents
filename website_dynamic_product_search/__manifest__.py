# -*- coding: utf-8 -*-
{
    # App information
    'name': 'Dynamic Website Product Search | Dynamic Product Search for Website',
    'category': 'Website',
    'version': '19.0.1.0',
    'summary': """This module allows website administrators to configure searchable product fields from the backend for the website shop and autocomplete search.
                Configure dynamic product search fields for website shop and autocomplete.

                Main Features:
                - Select searchable fields dynamically from Website settings
                - Supports product.template and product.product fields
                - Works with website shop search
                - Enhances autocomplete product search
                - Supports custom char, text, and html fields
                - No coding required for adding new searchable fields
                - Multi-website compatible

                Examples:
                - Search by Product Name
                - Search by Internal Reference
                - Search by Barcode
                - Search by Description
                - Search by Custom Fields

                'keywords': 
                -----------
                'odoo website search','product search',
                'website autocomplete','dynamic search fields',
                'website shop search','barcode search',
                'website_sale','odoo ecommerce search',
                'product filter','search products website',
                """,
    'description': """""",
    'license': 'OPL-1',

    # Dependencies
    'depends': ['website_sale'],

    # Views
    'data': ['views/website_view.xml'],

    # Odoo Store Specific
    'images': ['static/description/cover.gif'],

    # Author
    'author': 'Vraja Technologies',
    'website': 'http://www.vrajatechnologies.com',
    'maintainer': 'Vraja Technologies',
    'live_test_url': 'https://www.vrajatechnologies.com/contactus',

    # Technical
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': '25',
    'currency': 'EUR',
}