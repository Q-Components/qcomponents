{
    'name': 'FTP/SFTP IMPORT CSV/XLS FILE | All In One Import Record From FTP| All In One Import - Sales, Purchase, Accounts,Partner, Product, Inventory, BOM, CRM, Project | Import Product Template | Import Product Image | Import Product Variant | Import Sale Order Lines | Import Reordering Rules | Import Purchase Order Lines | All In One Import Record From SFTP | All In One Import Record From FTP | Import CSV File Manually',
    'version': '19.0.1.2',
    'category': 'Tool',
    'summary': """
    -Odoo all in one import for Sales, Purchase, Invoice, Inventory, Pricelist, BOM, Payment, Journal Entry, Picking, Product, Customer
    Import, All In One Import, Odoo All Import, Advance Data Import, Odoo All Import, All in One Import Images, Import Data, Import Files, Import Odoo Data - Import Partner, Import Product, Import Sales, Sales Data, Import Purchase, Import Accounts, Import Inventory, BOM, CRM, Project | Import Product Template | Import Product Variant | Import Product Image | Import Sale Order Lines | Import Reordering Rules| Import Purchase Order Lines | Picking | Chart of Accounts | Journal Entry| Import Bank Statement| Import Reordering Rules| Import Product Lines| Import Sales Order Lines | Import Stock Inventory | Import POS orders | Import Inventory Data | Import Products | Import Partners | Import Customers and Suppliers | Import Partner Data | Import Data - CSV | Import Data - XLS | Import Multiple Journal | Import Etsy| Import Amazon | Import Shopify | Odoo Integration | Import Pricelist | Odoo Google Data Import | Import Export | All in One Importable Line Views
    """,
    'description': """""",
    'depends': ['base','sale','stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/dynamic_import_records.xml',
        'views/sftp_syncing.xml',
        'views/ftp_syncing.xml',
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
    'price': '249',
    'currency': 'EUR',
    'license': 'OPL-1',
}
# version changelog
# 18.0.1.0 => Initial setup
# 18.0.1.1 => Split file concept added.
# 18.0.1.2 => Added default value field and added line in move when create/update quant with respective logs.
