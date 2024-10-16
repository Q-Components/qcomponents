{
    'name': 'All In One Import Record From SFTP || Import CSV File Manually',
    'version': '16.0.0',
    'category': 'Tool',
    'summary': """
    -Odoo all import for Sales, Purchase, Invoice, Inventory, Pricelist, BOM, Payment, Journal Entry, Picking, Product, Customer
    -All In One Import - Partner, Product, Sales, Purchase, Accounts, Inventory, BOM, CRM, Project | Import Product Template | Import Product Variant | Import Product Image | Import Sale Order Lines | Import Reordering Rules| Import Purchase Order Lines
    """,
    'description': """""",
    'depends': ['base','sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/dynamic_import_records.xml',
        'views/sftp_syncing.xml',
        'views/logs_details.xml',
        'wizard/dynamic_import_records_wizard.xml',
    ],
    "external_dependencies": {
        "python": ["xlrd", "binascii"],
    },
    'images': ['static/description/cover.gif'],
    'author': 'Vraja Technologies',
    'website': 'https://www.vrajatechnologies.com',
    'live_test_url': 'https://www.vrajatechnologies.com/contactus',
    'installable': True,
    'application': True,
    'autoinstall': False,
    'price': '69',
    'currency': 'EUR',
    'license': 'OPL-1',
}
# Version log
# 16.0.0 => Initial setup
