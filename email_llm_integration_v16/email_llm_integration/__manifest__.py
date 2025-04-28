{
    # App information
    'name': 'Email LLM Integration',
    'version': '16.0.1.0',
    'category': "Tool",
    'summary': """Automatically create quotations from AI-processed email inquiries.""",
    'license': 'OPL-1',
    'description': """This module reads emails from a configured mail server and processes only product inquiry emails using AI.
                      It analyzes the email content to identify the product and the context of the inquiry. 
                      Based on this, it automatically creates a quotation for the identified product.
                      | Automate Email Inquiry Processing | Email Inquiry Processing | Create Quotation from Email 
                      | AI Powered Email Inquiry Processing  |""",


    # Dependencies
    'depends': ['mail', 'sale_management', 'stock', 'account_accountant'],

    # Views
    'data': [
        'security/ir.model.access.csv',
        'views/email_llm.xml',
        'views/fetchmail_server.xml',
    ],

    'images': [],

    # Author
    'author': 'Vraja Technologies',
    'website': 'https://www.vrajatechnologies.com',
    'maintainer': 'Vraja Technologies',
    'live_test_url': 'https://www.vrajatechnologies.com/contactus',

    # Technical
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': '',
    'currency': 'EUR',
}

# version log:
# 28-04-2025 :: Migrated to the 16