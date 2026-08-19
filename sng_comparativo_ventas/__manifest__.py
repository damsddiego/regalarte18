# -*- coding: utf-8 -*-
{
    "name": "Comparativo de Ventas SNG",
    "version": "18.0.1.0.0",
    "author": "SNG",
    "license": "LGPL-3",
    "summary": "Reporte comparativo de ventas vs inventario por mes (últimos 6 meses).",
    "depends": [
        "base",
        "stock",
        "sale_management",
        "purchase",
        "sng_warehouse_group",
        "custom_ui_security",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/comparativo_wizard_views.xml",
        "views/comparativo_ventas_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sng_comparativo_ventas/static/src/js/action_manager.js",
        ],
    },
    "installable": True,
    "application": False,
}
