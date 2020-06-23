{
    # App information
    'name': 'BigCommerce Odoo Integration With Webhook',
    'category': 'Website',
    'author': "Vraja Technologies",
    'version': '13.0.7.12.2020',
    'summary': """BigCommerce Odoo Integration will help you connect with Market Place.""",
    'description': """""",

    'depends': ['bigcommerce_odoo_integration','stock'],

    'data': [
        "security/ir.model.access.csv",
        "data/res_group.xml",
        "views/bigcommerce_webhook_configuration_view.xml",
        "views/res_company.xml",
        "views/sale_order.xml",
        "views/stock_picking.xml",
    ],

    'images': ['static/description/bigcommerce_cover_image.png'],
    'maintainer': 'Vraja Technologies',
    'website': 'www.vrajatechnologies.com',

    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': '249',
    'currency': 'EUR',
    'license': 'OPL-1',

}
