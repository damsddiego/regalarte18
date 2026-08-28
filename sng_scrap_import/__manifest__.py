# -*- coding: utf-8 -*-
{
    "name": "SNG - Importar Desechos desde Excel",
    "version": "18.0.1.0.0",
    "author": "SNG",
    "license": "LGPL-3",
    "category": "Inventory",
    "summary": "Importa productos dañados desde Excel y crea órdenes de desecho",
    "depends": ["stock"],
    "data": [
        "security/ir.model.access.csv",
        "views/scrap_import_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
}
