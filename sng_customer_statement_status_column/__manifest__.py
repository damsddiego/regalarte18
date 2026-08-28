# -*- coding: utf-8 -*-
{
    "name": "Customer Statement Status Column",
    "version": "18.0.1.0.0",
    "category": "Accounting/Reporting",
    "summary": "Adds an invoice payment status indicator to the customer statement.",
    "author": "SNG",
    "license": "LGPL-3",
    "depends": ["account_reports"],
    "data": [
        "views/customer_statement_report.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sng_customer_statement_status_column/static/src/scss/customer_statement_status.scss",
        ],
        "account_reports.assets_pdf_export": [
            "sng_customer_statement_status_column/static/src/scss/customer_statement_status.scss",
        ],
    },
    "installable": True,
    "application": False,
}
