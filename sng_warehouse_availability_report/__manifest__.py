# -*- coding: utf-8 -*-
{
    "name": "SNG Warehouse Availability Report",
    "version": "18.0.1.1.0",
    "author": "SNG Cloud",
    "website": "https://sngcloud.com",
    "category": "Inventory/Reporting",
    "summary": "Reporte XLSX de disponibilidad por grupo de almacenes",
    "depends": [
        "purchase_stock",
        "report_xlsx",
        "sng_warehouse_group",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/warehouse_availability_line_views.xml",
        "wizard/warehouse_availability_wizard_views.xml",
        "report/warehouse_availability_reports.xml",
    ],
    "license": "LGPL-3",
    "application": False,
    "installable": True,
}
