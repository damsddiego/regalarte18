# -*- coding: utf-8 -*-
{
    "name": "SNG Notes on Sale Order Lines",
    "version": "18.0.1.0.0",
    "category": "Sales",
    "summary": "Agregar notas opcionales en las lineas de cotizaciones y pedidos",
    "description": """
        Este modulo agrega un campo de nota opcional en cada linea de
        cotizacion y pedido de venta, visible tambien en el PDF.
    """,
    "author": "SNG CLOUD",
    "website": "https://www.sngcloud.com",
    "license": "LGPL-3",
    "depends": ["sale_stock"],
    "data": [
        "views/sale_order_views.xml",
        "views/stock_picking_views.xml",
        "report/sale_order_report_templates.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
