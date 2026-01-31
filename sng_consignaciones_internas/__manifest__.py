# -*- coding: utf-8 -*-
{
    "name": "Entrega de consignaciones internas",
    "version": "18.0.1.0.0",
    "author": "SNG Cloud",
    "website": "https://sngcloud.com",
    "category": "Inventory",
    "summary": "Traslados internos con precios para entregas en consignación",
    "depends": ["stock"],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "data/stock_picking_type.xml",
        "report/consignacion_report.xml",
        "report/consignacion_report_templates.xml",
        "views/stock_picking_views.xml",
    ],
    "license": "LGPL-3",
    "application": False,
    "installable": True,
}
