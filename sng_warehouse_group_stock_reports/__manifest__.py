# -*- coding: utf-8 -*-
{
    "name": "SNG Warehouse Groups - Native Stock Reports",
    "version": "18.0.1.0.0",
    "author": "SNG Cloud",
    "website": "https://sngcloud.com",
    "category": "Inventory/Reporting",
    "summary": "Agrega grupos de almacenes a filtros de reportes nativos de inventario",
    "depends": [
        "sng_warehouse_group",
        "stock_account",
    ],
    "data": [
        "views/stock_report_search_views.xml",
    ],
    "license": "LGPL-3",
    "application": False,
    "installable": True,
}
