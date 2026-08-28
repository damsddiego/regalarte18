# -*- coding: utf-8 -*-
{
    "name": "Customer Statement Partner Header",
    "version": "18.0.1.0.0",
    "category": "Accounting/Reporting",
    "summary": "Shows the customer's commercial name, address, phone and email "
               "in the customer statement PDF header (single-partner statements).",
    "author": "SNG",
    "license": "LGPL-3",
    "depends": [
        "account_reports",
        "sng_custom_name_partner",
    ],
    "data": [
        "views/customer_statement_header.xml",
    ],
    "installable": True,
    "application": False,
}
