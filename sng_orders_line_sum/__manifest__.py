# -*- coding: utf-8 -*-
{
    "name": "SNG Orders and Invoice Line Sum",
    "version": "18.0.2.0.0",
    "category": "Sales",
    "summary": "Número de línea y totales de líneas y cantidades en ventas y facturas",
    "description": """
        Agrega un número de línea secuencial visible a la izquierda de las líneas
        de cotización/orden de venta y una sumatoria de cantidades solicitadas.
        En facturas muestra el total de líneas de producto y la suma de cantidades.
    """,
    "author": "SNG",
    "license": "LGPL-3",
    "depends": ["sale", "account"],
    "data": [
        "views/sale_order_views.xml",
        "views/account_move_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
