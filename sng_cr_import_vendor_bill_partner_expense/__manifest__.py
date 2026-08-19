# -*- coding: utf-8 -*-
{
    "name": "SNG CR Import Vendor Bill Partner Expense",
    "summary": "Cuenta de gasto por proveedor para facturas de proveedor",
    "version": "18.0.1.1.0",
    "category": "Accounting",
    "author": "SNG",
    "license": "LGPL-3",
    "depends": [
        "account",
        "cr_import_vendor_bills",
    ],
    "data": [
        "data/migrate_expense_account.xml",
        "views/res_partner_views.xml",
    ],
    "installable": True,
    "application": False,
}
