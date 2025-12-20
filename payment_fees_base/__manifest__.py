# -*- coding: utf-8 -*-

{
    "name": "Payment Fees Base",
    "version": "19.0.1.0",
    "author": "Craftsync Technologies",
    "maintainer": "Craftsync Technologies",
    "category": "Accounting",
    "summary": """Collect Payment processing fees from customer. Fees can be configured
as fixed or percentage wise.""",
    "description": """
Payment Provider Fees Extension: Collect Payment processing fees from customer.
""",
    "website": "https://www.craftsync.com",
    "license": "OPL-1",
    "support": "info@craftsync.com",
    "depends": ["payment"],
    "data": [
        "views/payment_provider_views.xml",
        "views/payment_transaction_views.xml",
        "views/payment_form_template.xml",
    ],
    "demo": [],
    "application": True,
    "auto_install": False,
    "images": ["static/description/main_screen.png"],
    "price": 29.99,
    "currency": "USD",
}
