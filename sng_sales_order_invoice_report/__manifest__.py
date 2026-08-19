# -*- coding: utf-8 -*-
{
    "name": "SNG Sales Order Invoice Report",
    "version": "18.0.1.0.0",
    "category": "Sales/Reporting",
    "summary": "Reporte de ordenes ingresadas vs no facturadas vs facturadas por vendedor contacto",
    "author": "SNG",
    "license": "LGPL-3",
    "depends": [
        "sale",
        "sales_commission_omax",
        "report_xlsx",
    ],
    "data": [
        "security/ir.model.access.csv",
        "report/sales_order_invoice_report_xlsx.xml",
        "views/sales_order_invoice_report_views.xml",
        "views/sales_order_invoice_report_wizard_views.xml",
        "views/sales_order_invoice_report_menus.xml",
    ],
    "application": False,
    "installable": True,
}
