# -*- coding: utf-8 -*-

{
    "name": "SNG Productos Facturados por Cliente",
    "version": "18.0.2.0.0",
    "category": "Accounting/Reporting",
    "summary": (
        "Detalle y resumen de productos facturados por cliente, "
        "neto de notas de crédito"
    ),
    "author": "SNG",
    "license": "LGPL-3",
    "depends": [
        "account",
        "web",
        "report_xlsx",
    ],
    "data": [
        "security/customer_product_report_security.xml",
        "security/ir.model.access.csv",
        "views/customer_product_report_line_views.xml",
        "views/product_customer_report_line_views.xml",
        "wizard/customer_product_report_wizard_views.xml",
        "wizard/product_customer_report_wizard_views.xml",
        "report/customer_product_report_actions.xml",
        "report/product_customer_report_actions.xml",
        "report/customer_product_report_templates.xml",
        "report/product_customer_report_templates.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
