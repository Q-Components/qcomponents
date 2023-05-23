{
    'name': 'QC INVOICE REPORT',
    'version': '16.23.05.2023',
    'Summary': 'Invoice Report',
    'description': '',
    'license': 'OPL-1',
    'depends': ['account', 'sale_stock','skuvault_odoo_integration','qcomponents_sale'],
    'data': [
        'views/account_move_line.xml'
    ],
    'installable': True,
    'application': True,
    'auto_install': False
}
