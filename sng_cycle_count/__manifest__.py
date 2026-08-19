# -*- coding: utf-8 -*-
{
    "name": "Conteos Cíclicos Diarios",
    "version": "18.0.1.2.0",
    "category": "Inventory",
    "summary": "Automatización de conteos cíclicos diarios con selección inteligente y conciliación en tiempo real",
    "author": "SNG",
    "license": "AGPL-3",
    "depends": ["stock", "product", "report_xlsx", "sng_analisis_compras"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "data/ir_cron.xml",
        "views/cycle_count_config_views.xml",
        "views/cycle_count_views.xml",
        "report/report_discrepancy_pdf.xml",
        "report/report_actions.xml",
    ],
    "application": False,
    "installable": True,
}
