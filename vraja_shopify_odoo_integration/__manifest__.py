# -*- coding: utf-8 -*-pack
{  # App information
    'name': 'Shopify to Odoo Connector',
    'category': '',
    'version': '16.0',
    'summary': """Merge & Supervise Shopify Activities in Odoo through the Implementation of Shopify Integration. """,
    'description': """ 
            """,
    'depends': ['delivery', 'sale_stock', 'sale_management', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/shopify_operations_view.xml',
        'data/product_data.xml',
        'data/cron.xml',
        'wizard/prepare_product_for_export_shopify_instance.xml',
        'wizard/export_product_to_shopify.xml',
        'views/order_workflow_automation.xml',
        'views/shopify_location.xml',
        'views/shopify_payment_gateway.xml',
        'views/shopify_financial_status_configuration.xml',
        'views/shopify_log.xml',
        'views/order_data_queue.xml',
        'views/product_listing.xml',
        'views/product_listing_item.xml',
        'views/product_data_queue.xml',
        'views/inventory_data_queue.xml',
        'views/sale_order.xml',
        'views/ir_cron.xml',
        'views/shopify_instance_integration.xml',
        'views/customer_data_queue.xml',
        'views/res_partner_view.xml',
        'views/menu_item.xml',
        'views/delivery_carrier.xml',
        'views/stock_picking.xml',
        'views/shopify_product_image.xml',
        'views/account_move.xml',
    ],

    'images': ['static/description/icon.png'],
    'author': 'Vraja Technologies',
    'maintainer': 'Vraja Technologies',
    'website': 'https://www.vrajatechnologies.com',
    'live_test_url': 'https://www.vrajatechnologies.com/contactus',
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'OPL-1',
}
