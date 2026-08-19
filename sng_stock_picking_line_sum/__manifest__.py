# -*- coding: utf-8 -*-
{
    "name": "SNG Stock Picking Line Sum",
    "version": "18.0.1.1.0",
    "category": "Inventory",
    "summary": "Número de línea y sumatorias en todas las transferencias de inventario",
    "description": """
        Agrega un número de línea secuencial visible a la izquierda de las líneas
        de operaciones en recepciones, entregas y transferencias internas.
        También agrega sumatorias de demanda y cantidad realizada.
    """,
    "author": "SNG",
    "license": "LGPL-3",
    "depends": ["stock"],
    "data": [
        "views/stock_picking_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
