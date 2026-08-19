# -*- coding: utf-8 -*-
{
    "name": "Análisis de Compras SNG",
    "version": "18.0.1.6.0",
    "author": "SNG",
    "license": "LGPL-3",
    "category": "Purchases/Reporting",
    "summary": (
        "Reporte unificado: historial de ventas por mes vs inventario y "
        "sugerido de compras basado en ventas facturadas."
    ),
    "description": """
Unifica los reportes 'Comparativo de Ventas SNG' (sng_comparativo_ventas) y
'SNG Purchase Suggestion Report' (sng_purchase_suggestion_report) en un solo
wizard. Fuente de ventas: facturas contabilizadas (neto de notas de crédito),
con atribución a almacén/ubicación de venta. Convive con los módulos
originales durante el período de validación.
    """,
    "depends": [
        "account",
        "purchase_stock",
        "sale_management",
        "stock",
        "report_xlsx",
        "sale_stock_sng",
        "sng_warehouse_group",
        "custom_ui_security",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/analisis_compras_line_views.xml",
        "wizard/analisis_compras_wizard_views.xml",
        "report/analisis_compras_reports.xml",
    ],
    "installable": True,
    "application": False,
}
