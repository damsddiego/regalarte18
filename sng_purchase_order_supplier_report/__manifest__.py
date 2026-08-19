# -*- coding: utf-8 -*-

{
    "name": "SNG Órdenes de Compra por Proveedor",
    "version": "18.0.1.0.0",
    "category": "Purchases/Reporting",
    "summary": (
        "Resumen y detalle de órdenes de compra por proveedor, "
        "incluyendo productos en tránsito"
    ),
    "author": "SNG",
    "license": "LGPL-3",
    "depends": [
        "purchase_stock",
        "report_xlsx",
        "web",
    ],
    "data": [
        "security/purchase_supplier_report_security.xml",
        "security/ir.model.access.csv",
        "views/purchase_supplier_report_line_views.xml",
        "wizard/purchase_supplier_report_wizard_views.xml",
        "report/purchase_supplier_report_actions.xml",
        "report/purchase_supplier_report_templates.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}

