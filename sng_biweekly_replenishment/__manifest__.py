# -*- coding: utf-8 -*-
{
    "name": "SNG Reabastecimiento Bisemanal",
    "version": "18.0.1.0.0",
    "category": "Inventory/Operations",
    "summary": "Demanda, alertas y traslados bisemanales entre almacenes",
    "author": "SNG Cloud",
    "website": "https://sngcloud.com",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "mail",
        "report_xlsx",
        "sng_warehouse_group",
    ],
    "data": [
        "security/replenishment_security.xml",
        "security/ir.model.access.csv",
        "data/sequence_data.xml",
        "data/ir_cron_data.xml",
        "views/replenishment_config_views.xml",
        "views/replenishment_batch_views.xml",
        "views/replenishment_alert_views.xml",
        "views/stock_picking_views.xml",
        "report/replenishment_reports.xml",
        "report/replenishment_report_templates.xml",
        "views/replenishment_menus.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}

