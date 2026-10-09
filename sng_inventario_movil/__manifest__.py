# -*- coding: utf-8 -*-
{
    "name": "Inventario móvil (app Android con lector)",
    "summary": "Inventario físico desde la app Android con lector de código de "
               "barras: conteo ciego, reconteo de diferencias y ajuste aplicado "
               "por Gerencia.",
    "version": "18.0.1.1.0",
    "category": "Inventory/Inventory",
    "author": "SNG",
    "website": "https://sngcloud.com",
    "license": "LGPL-3",
    "depends": [
        "stock_account",
        "mail",
        "sng_inventory_adjustment_history",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence.xml",
        "report/acta_inventario.xml",
        "views/sng_inventario_sesion_views.xml",
    ],
    "installable": True,
    "application": False,
}
