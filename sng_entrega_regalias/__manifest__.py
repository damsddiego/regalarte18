# -*- coding: utf-8 -*-
{
    "name": "SNG Entrega de Regalías",
    "version": "18.0.1.0.0",
    "author": "SNG Cloud",
    "website": "https://sngcloud.com",
    "category": "Inventory",
    "summary": "Entrega de productos de regalía a clientes con rebajo de inventario, asiento contable y comprobante PDF",
    "description": """
Entrega de Regalías a Clientes
==============================

Documento para entregar productos de obsequio a clientes:

- Rebaja inventario mediante una transferencia de salida desde el almacén elegido.
- Genera y publica un asiento contable al costo del producto (débito gasto de regalías / crédito contrapartida de inventario), con cuentas y diario configurables en Ajustes de Contabilidad.
- Imprime un comprobante PDF de entrega.
- Dos niveles de seguridad: Usuario regalías (borradores) y Responsable regalías (valida y configura).
""",
    "depends": ["stock", "account"],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "data/stock_data.xml",
        "views/res_config_settings_views.xml",
        "views/regalia_views.xml",
        "report/regalia_report.xml",
        "report/regalia_report_templates.xml",
    ],
    "license": "LGPL-3",
    "application": False,
    "installable": True,
}
