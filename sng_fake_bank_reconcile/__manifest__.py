# -*- coding: utf-8 -*-
{
    "name": "SNG Conciliación Falsa Bancaria",
    "version": "18.0.1.0.0",
    "category": "Accounting/Bank",
    "summary": "Sugiere pagos de clientes para líneas de extracto bancario sin conciliar contablemente.",
    "author": "SNG",
    "license": "LGPL-3",
    "depends": [
        "account",
        "account_bank_statement_import",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/sng_fake_reconcile_config_views.xml",
        "views/account_bank_statement_line_views.xml",
        "views/menu.xml",
    ],
    "installable": True,
    "application": False,
}
