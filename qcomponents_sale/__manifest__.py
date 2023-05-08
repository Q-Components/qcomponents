{
    'name': "QComponents: Sale Action",

    'summary': """
        Server Action to select and add products to a new Sales Order.""",

    'description': """
        Development ID: 2154376 - CIC
        
        Products -> Switch to line view -> Select multiple products -> Action -> Add to a new SO lines 

        It directly takes you to the new SO created with the multiple SO lines pre populated. 

        The client can now add the customer and according to the Pricelist selection, the SO line unit prices are updated along with subtotal amount.
    """,

    'author': "Odoo PS-US",
    'website': "http://www.odoo.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/13.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Custom Development',
    'version': '1.0',

    # any module necessary for this one to work correctly
    'depends': ['sale', 'product', 'contacts'],

    # always loaded
    'data': [
        #'data/qcomponents_action.xml',
    ],
    'license': 'OPL-1',
}
