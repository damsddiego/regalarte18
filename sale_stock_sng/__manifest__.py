# -*- coding: utf-8 -*-
{
    "name": "Sale Stock CR",
    "version": "18.0.1.0.3",
    "author": "SNG Cloud",
    "website": "https://sngcloud.com",
    "category": "Sale",
    "summary": "",
    "depends": ["sale_stock", "report_xlsx", "partner_client_code"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_partner_views.xml",
"views/stock_quant_views.xml",
        "wizards/reports.xml",
        "wizards/consign_cxc_wizard_views.xml"
    ],
    "license": "LGPL-3",
    "application": False,
    "installable": True,
}
