{
    'name': 'QC INVOICE REPORT',
    'version': '16.03.03.2022',
    'Summary': 'Invoice Report',
    'description': '',
    'license': 'OPL-1',
    'depends': ['account', 'sale_stock','skuvault_odoo_integration'],
    'data': [
        'views/account_move_line.xml'
    ],
    'installable': True,
    'application': True,
    'auto_install': False
}
