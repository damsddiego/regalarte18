# -*- coding: utf-8 -*-
{
    "name": "SNG Purchase Suggestion Report",
    "version": "18.0.1.1.0",
    "author": "SNG Cloud",
    "website": "https://sngcloud.com",
    "category": "Purchases/Reporting",
    "summary": "Reporte sugerido de compras basado en ventas facturadas y existencias",
    "depends": [
        "account",
        "purchase_stock",
        "report_xlsx",
        "sale_stock_sng",
        "sng_warehouse_group",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/purchase_suggestion_line_views.xml",
        "wizard/purchase_suggestion_wizard_views.xml",
        "report/purchase_suggestion_reports.xml",
    ],
    "license": "LGPL-3",
    "application": False,
    "installable": True,
}
