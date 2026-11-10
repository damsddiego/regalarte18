# -*- coding: utf-8 -*-
{
    "name": "SNG Warehouse Groups - Native Stock Reports",
    "version": "18.0.1.1.0",
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
        "views/product_at_date_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sng_warehouse_group_stock_reports/static/src/views/**/*",
        ],
    },
    "license": "LGPL-3",
    "application": False,
    "installable": True,
}
