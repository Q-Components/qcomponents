# -*- coding: utf-8 -*-
{
    # App information
    "name": 'OneDrive Odoo Integration | OneDrive Storage |  Microsoft OneDrive Sync | Odoo OneDrive Connector',
    "category": "Documents",
    "version": "19.0.1.0",
    "summary": '''Integrate Microsoft OneDrive with Odoo for seamless cloud file management.
        Auto-create and map OneDrive folders to any Odoo record (Sales Orders, Invoices, Contacts, Projects, and more) using Smart Folder Mapping Rules.
        Automatically upload Odoo attachments to OneDrive and import OneDrive files directly into Odoo Documents.
        Real-time sync powered by Microsoft Graph API Webhooks — changes in OneDrive reflect instantly in Odoo.
        Supports file upload, download, delete, restore, and rename with full sync history logs.
        Monitor OneDrive storage quota and usage directly from the Odoo Dashboard.
        Built-in interactive Folder Picker for easy OneDrive folder selection.
        Compatible with OneDrive Personal, OneDrive for Business, and Microsoft 365 SharePoint-backed drives.

        Odoo OneDrive Integration | Microsoft OneDrive Connector | Odoo Cloud Storage | OneDrive Document Management | Odoo Attachment Sync | 
        Microsoft 365 Integration | Odoo File Management | OneDrive File Synchronization | Odoo Documents Integration | Odoo Cloud File Sync | 
        Microsoft Graph API Integration | Odoo Attachment Backup | Odoo Document Automation | OneDrive Storage Integration | Odoo File Upload Automation | 
        Odoo External Document Storage | Odoo Smart Folder Mapping | Odoo Document Sync | OneDrive for Business Integration | Odoo Cloud Document Management''',
    'description': "",
    "license": "OPL-1",

    # Dependencies
    "depends": ["sale_management", "documents"],

    # Views
    "data": [
        "security/ir.model.access.csv",
        "data/cron_data.xml",
        "views/onedrive_folder_rule.xml",
        "views/onedrive_configuration.xml",
        "views/onedrive_sync_history_views.xml",
        "views/onedrive_dashboard_views.xml",
        "wizard/import_wizard.xml",
        "wizard/onedrive_folder_picker_views.xml",
    ],

    'assets': {
        'web.assets_backend': [
            'onedrive_integration_vts/static/src/js/import_button.js',
            'onedrive_integration_vts/static/src/js/onedrive_search_panel.js',
            'onedrive_integration_vts/static/src/xml/import_button.xml',
            # Dashboard
            'onedrive_integration_vts/static/src/css/onedrive_dashboard.css',
            'onedrive_integration_vts/static/src/js/onedrive_dashboard.js',
            'onedrive_integration_vts/static/src/xml/onedrive_dashboard.xml',
        ],
    },

    # Odoo Store Specific
    'images': ['static/description/cover.gif'],

    # Author
    "author": "Vraja Technologies",
    "website": "http://www.vrajatechnologies.com",
    "maintainer": "Vraja Technologies",
    "live_test_url": "http://www.vrajatechnologies.com/contactus",

    # Technical
    "demo": [],
    "installable": True,
    "application": True,
    "auto_install": False,
    "price": '99',
    "currency": "EUR",
}
