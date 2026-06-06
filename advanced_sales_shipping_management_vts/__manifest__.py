# -*- coding: utf-8 -*-
{
    # App information
    "name": "Advanced Sales & Shipping Management | Shipping & Order Discount | Shipping Surcharges | Sales Dashboard | Sales Order Advance Payment",
    "category": "Sales",
    "version": "19.0.1.0",
    "summary": """Enhance Odoo Sales and Delivery operations with advanced shipping cost management and
      customer-specific discount controls. Configure Shipping Discount, Insurance Fees, Fuel Surcharges, and Remote Area
      Surcharges for accurate shipping cost calculations. Automatically apply customer-wise discounts on sales orders,
      register payments directly from the sales order. The module also includes an interactive Sales Dashboard with
      Today, Weekly, Monthly, Pending Orders, Pending Deliveries, and Overdue Quotations. Also includes convenient
       Today, Weekly, Monthly, Quarterly and Unshipped sales order filters for improved sales analysis and order tracking.""",
    "description": """sales management, shipping management, shipping discount, sales order discount, customer-specific discount, shipping surcharge, fuel surcharge, insurance charge, remote area surcharge, shipping cost calculation, sales dashboard, sales statistics, advance payment, sales order advance payment, quotation tracking, pending orders, pending deliveries, sales order filters, order management, Odoo sales automation""",
    "license": "OPL-1",

    # Dependencies
    "depends": ["sale_management","delivery",],

    # Views
    "data": [
        "security/ir.model.access.csv",
        "wizard/choose_delivery_carrier_view.xml",
        "wizard/payment_wizard.xml",
        "views/res_partner_view.xml",
        "views/sale_order_view.xml",
    ],
    # assets
    'assets': {
        'web.assets_backend': [
            'advanced_sales_shipping_management_vts/static/src/js/sale_dashboard.js',
            'advanced_sales_shipping_management_vts/static/src/xml/sale_dashboard.xml',
        ],
    },
    
    # Odoo Store Specific
    'images': ['static/description/cover.gif'],

    # Author
    "author": "Vraja Technologies",
    "website": "www.vrajatechnologies.com",
    "maintainer": "Vraja Technologies",
    "live_test_url": "http://www.vrajatechnologies.com/contactus",

    # Technical
    "demo": [],
    "installable": True,
    "application": True,
    "auto_install": False,
    "price": "49",
    "currency": "EUR",
}
