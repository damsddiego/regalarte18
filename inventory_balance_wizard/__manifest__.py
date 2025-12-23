# -*- coding: utf-8 -*-
{
    "name": "Inventory Balance - Wizard",
    "version": "18.0.1.0.0",
    "category": "Inventory",
    "summary": "Wizard para filtrar inventario por almacén/ubicaciones/productos/categorías",
    "depends": ["stock", "product", "report_xlsx"],
    "data": [
        "security/ir.model.access.csv",
        "wizards/inventory_balance_wizard_views.xml",
        "reports/inventory_balance_xlsx_report.xml",
    ],
    "application": False,
    "installable": True,
    "license": "LGPL-3",
}
