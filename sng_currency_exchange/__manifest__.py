# -*- coding: utf-8 -*-
{
    "name": "Tipo de Cambio Personalizado",
    "version": "18.0.1.0.0",
    "author": "SNG Cloud",
    "website": "https://sngcloud.com",
    "category": "Accounting",
    "summary": "Permite establecer un tipo de cambio personalizado en facturas y listas de precio",
    "description": """
        Este módulo permite establecer un tipo de cambio personalizado en
        facturas y un tipo de cambio fijo en listas de precio de venta,
        conservando la tasa desde la cotización hasta la factura.
    """,
    "depends": ["account", "sale"],
    "data": [
        "views/product_pricelist_views.xml",
        "views/sale_order_views.xml",
        "views/account_move_views.xml",
    ],
    "license": "LGPL-3",
    "application": False,
    "installable": True,
}
