# -*- coding: utf-8 -*-
{
    "name": "Reporte Consignaciones",
    "version": "18.0.1.0.0",
    "author": "SNG",
    "license": "LGPL-3",
    "category": "Inventory/Reporting",
    "summary": "Resumen de consignaciones por cliente: fechas de movimiento y valor de inventario",
    "depends": [
        "account",
        "sale_stock_sng",
        "sng_sales_routes",
        "sales_commission_omax",
        "customer_sequence",
        "sng_custom_name_partner",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizards/consignment_report_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
