# -*- coding: utf-8 -*-
{
    "name": "Bodegas Consignación",
    "version": "18.0.1.0.0",
    "category": "Inventory/Reporting",
    "summary": "Reporte de stock y valor por bodegas de consignación",
    "author": "SNG",
    "depends": [
        "stock",
        "product",
        "sale",
        "report_xlsx",
        "sale_stock_sng",
        "sng_currency_exchange",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizards/consignment_warehouse_report_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
