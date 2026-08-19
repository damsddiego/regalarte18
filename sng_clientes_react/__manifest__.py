# -*- coding: utf-8 -*-
{
    "name": "Clientes Nuevos-React",
    "version": "18.0.1.0.0",
    "category": "Contacts/Reporting",
    "summary": "Reporte de clientes nuevos y reactivados por mes",
    "author": "SNG",
    "license": "LGPL-3",
    "depends": [
        "contacts",
        "customer_sequence",
        "sng_sales_routes",
        "sales_commission_omax",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/new_reactivated_customer_report_views.xml",
        "views/new_reactivated_customer_report_wizard_views.xml",
        "views/new_reactivated_customer_report_menus.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
