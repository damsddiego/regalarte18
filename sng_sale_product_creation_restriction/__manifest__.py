# -*- coding: utf-8 -*-
{
    "name": "SNG Restricción de Creación Rápida de Productos",
    "version": "18.0.1.1.0",
    "category": "Inventory",
    "summary": "Evita crear productos accidentalmente desde cotizaciones y traslados",
    "author": "SNG",
    "license": "LGPL-3",
    "depends": ["sale", "stock"],
    "data": [
        "views/sale_order_views.xml",
        "views/stock_picking_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
