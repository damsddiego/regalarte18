# -*- coding: utf-8 -*-
{
    "name": "SNG Stock Scrap Import",
    "version": "18.0.1.0.0",
    "category": "Inventory",
    "summary": "Importa desechos de inventario desde Excel hacia stock.scrap",
    "author": "SNG",
    "license": "LGPL-3",
    "depends": ["stock", "product"],
    "external_dependencies": {
        "python": ["openpyxl"],
    },
    "data": [
        "security/ir.model.access.csv",
        "wizard/stock_scrap_import_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
}
