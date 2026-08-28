# -*- coding: utf-8 -*-
{
    "name": "SNG Inventory Adjustment History",
    "version": "18.0.1.1.0",
    "author": "SNG Cloud",
    "website": "https://sngcloud.com",
    "category": "Inventory/Inventory",
    "summary": "Historial de ajustes para grupos de almacenes",
    "depends": [
        "stock_account",
        "sng_warehouse_group",
        "custom_ui_security",
    ],
    "data": [
        "security/inventory_adjustment_history_security.xml",
        "security/ir.model.access.csv",
        "data/mail_templates.xml",
        "views/inventory_adjustment_history_views.xml",
        "views/warehouse_group_views.xml",
    ],
    "license": "LGPL-3",
    "application": False,
    "installable": True,
}

