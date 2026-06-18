# -*- coding: utf-8 -*-pack
{
    # App information
    'name': 'Sales Dashboard',
    'version': '19.0.1.0',
    'sequence': 1,
    'category': 'Sales',
    'summary': """
    The Sales Dashboard gives a complete, real-time view of business performance on one screen, with a date filter that updates everything instantly. Twelve KPI cards track sales, orders, quotations, invoices, payments, deliveries, profit, and shipping costs, each with month-over-month change and most clickable for drill-down detail.

    Below that, charts cover sales trends, top products and customers, city-wise demand, invoice and delivery status, and carrier shipping costs, while an Alerts panel flags issues like stock shortages, overdue invoices, and delayed deliveries that need action.


    Sales Dashboard
    Tableau de bord des ventes
    Panel de ventas
    Verkoopdashboard

    Monthly Sales Trend
    Évolution mensuelle des ventes
    Tendencia de ventas mensuales
    Maandelijkse verkooptrend

    Top Products and Customers
    Principaux produits et clients
    Principales productos y clientes
    Topproducten en -klanten

    Pending Delivery Tracking
    Suivi de livraison en attente
    Seguimiento de entrega pendiente
    Volgen van levering in afwachting

    Sales Analytics
    Analyse des ventes
    Análisis de ventas
    Verkoopanalyse
""",
    'license': 'OPL-1',
    'description': """""",

    # Dependencies
    'depends': ['sale_management','stock','stock_delivery'],

    # Views
    'data': [
        'views/sales_dashboard_action.xml',
        ],

    'assets': {
       'web.assets_backend': [
           'sales_dashboard_vts/static/src/js/dashboard.js',
           'sales_dashboard_vts/static/src/xml/dashboard.xml',
           'sales_dashboard_vts/static/src/scss/dashboard.scss',
       ],
    },
    
    'images': ['static/description/cover.gif'],
    # Author
    'author': 'Vraja Technologies',
    'website': 'www.vrajatechnologies.com',
    'maintainer': 'Vraja Technologies',

    # Technical
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'currency': '',
    'price': "",
}

