# -*- coding: utf-8 -*-
{
    "name": "SNG Diario sin Documentos Electrónicos",
    "version": "18.0.1.0.0",
    "category": "Accounting",
    "summary": "Diario de compras dedicado para facturas de proveedor sin FE, con numeración estándar de Odoo",
    "author": "SNG",
    "license": "LGPL-3",
    "depends": ["account", "cr_electronic_invoice"],
    "data": [
        "views/account_journal_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
