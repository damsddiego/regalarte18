# -*- coding: utf-8 -*-
{
    "name": "SNG Statement Order by Invoice",
    "version": "18.0.1.0.0",
    "category": "Accounting/Reporting",
    "summary": "Ordena el estado de cuenta agrupando facturas con sus pagos y notas de crédito.",
    "description": """
Este módulo modifica el reporte de estado de cuenta de clientes para que,
dentro de cada cliente, las líneas aparezcan agrupadas por factura:

1. Primero la factura (out_invoice).
2. A continuación los pagos y notas de crédito reconciliados con esa factura.
3. Luego la siguiente factura y sus documentos relacionados.

Esto facilita la lectura del estado de cuenta al mantener juntos todos los
movimientos que afectan una misma factura.
    """,
    "author": "SNG",
    "license": "LGPL-3",
    "depends": ["account_reports"],
    "installable": True,
    "application": False,
}
