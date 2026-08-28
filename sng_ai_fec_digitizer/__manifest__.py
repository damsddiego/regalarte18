# -*- coding: utf-8 -*-
{
    "name": "SNG AI FEC Digitizer",
    "version": "18.0.1.0.0",
    "category": "Accounting/Accounting",
    "summary": "Digitaliza comprobantes escaneados y prepara FEC revisables",
    "author": "SNG",
    "license": "LGPL-3",
    "depends": [
        "account",
        "mail",
        "sng_ai_dashboard",
        "cr_electronic_invoice",
        "sng_cr_import_vendor_bill_partner_expense",
    ],
    "external_dependencies": {
        "python": ["anthropic", "requests", "PyPDF2", "pypdfium2", "PIL"],
    },
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/res_config_settings_views.xml",
        "views/fec_digitizer_views.xml",
        "views/account_move_views.xml",
    ],
    "installable": True,
    "application": False,
}

