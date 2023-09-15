# -*- coding: utf-8 -*-
#################################################################################
# Author      : Ashish Hirpara (<ashish-hirpara.com>)
# Copyright(c): 2021
# All Rights Reserved.
#
# This module is copyright property of the author mentioned above.
# You can`t redistribute it.
#
#################################################################################
{
    'name': "Multiple Websites per Product | Multiple Websites per Category | Multi website selection for products | Bulk website assign",
    'version': '14.0.0.0.0',

    'summary': """ Add multiple websites per product in Odoo multi website, 
                Odoo Multi Website, Multi website Select, 
                Add product into multiple website, Website select in bulk, 
                Bulk website select, Bulk website assign, Bulk website,
                Multi websites per product, multiple websites,
                Product in multi website, Multi websites per category,
                Add category into multiple website,
                Add multiple websites per category in Odoo multi website,
                Bulk website select in product category,
                Multi website odoo
                 """,

    'description': """ Add Multiple Websites per product and eCommerce category in Odoo multi website.
        With this app you can add a product to several websites instead of just one or all at the time.
        Odoo's core multi website feature only allows you to select one website per product or all at, 
        but it doesn't allow you to select 2 or more websites per product or category.   """,

    'sequence': 6,
    'author': 'Ashish Hirpara',
    'license': 'OPL-1',
    'website': 'https://ashish-hirpara.com/',

    'currency': 'USD',
    'price': "64",
    'maintainer': 'Ashish Hirpara',
    'category': 'Website',

    'support': 'hello@ashish-hirpara.com',
    'images': ['static/description/banner.png'],

    'depends': ['base_multi_website_selection','website_sale'],

    'data': [
        'data/action.xml',
        'views/product_template_view.xml',
        'views/product_public_category_view.xml',
        'views/product_product_view.xml',
        'views/templates.xml',
    ],


}
