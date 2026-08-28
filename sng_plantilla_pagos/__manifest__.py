# -*- coding: utf-8 -*-
{
    "name": "SNG Plantilla Pagos",
    "version": "18.0.1.2.0",
    "category": "Accounting",
    "summary": "Agrega logo e informacion de compania al recibo de pagos",
    "author": "SNG",
    "license": "LGPL-3",
    "depends": [
        "account",
        "customer_sequence",
        "sales_commission_omax",
        "sng_custom_name_partner",
        "sng_sales_routes",
    ],
    "data": [
        "report/payment_receipt_templates.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
