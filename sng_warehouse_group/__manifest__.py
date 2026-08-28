# -*- coding: utf-8 -*-
{
    "name": "SNG Warehouse Groups",
    "version": "18.0.1.0.0",
    "author": "SNG Cloud",
    "website": "https://sngcloud.com",
    "category": "Inventory/Configuration",
    "summary": "Agrupa almacenes para reutilizarlos como filtros en reportes",
    "depends": [
        "stock",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/warehouse_group_views.xml",
    ],
    "license": "LGPL-3",
    "application": False,
    "installable": True,
}
