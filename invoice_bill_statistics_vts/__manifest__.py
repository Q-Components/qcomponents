# -*- coding: utf-8 -*-
{
    # App information
    "name": "Invoice & Bill Statistics | Overdue & Unpaid Invoices and Bills",
    "category": "Accounting",
    "version": "19.0.1.0",
    "summary": """Enhance Odoo Accounting with a clear and informative dashboard for Customer Invoices and Vendor
      Bills. Easily monitor today's, weekly, and monthly invoice and bill amounts, and keep track of unpaid, partially
      paid, and overdue invoices and bills. The module also provides convenient Today, This Week, This Month, and This
      Quarter filters, making it easier to review and manage Invoice and Bill records.""",
    "description": """invoice statistics, bill statistics, customer invoices, vendor bills, unpaid invoices, overdue invoices, partially paid invoices, unpaid bills, overdue bills, payment tracking, receivables management, payables management, accounting analytics, accounting insights, invoice analysis, bill analysis, date filters, financial reporting, Odoo accounting, invoice and bill management""",
    "license": "OPL-1",

    # Dependencies
    "depends": ["account"],

    # Views
    "data": [
        "views/account_move.xml",
    ],
    # assets
    'assets': {
        'web.assets_backend': [
            'invoice_bill_statistics_vts/static/src/js/account_move_dashboard.js',
            'invoice_bill_statistics_vts/static/src/xml/account_move_dashboard.xml',
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
