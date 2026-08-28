# -*- coding: utf-8 -*-
{
    'name': 'SNG Ruteros - Recibos de pago',
    'summary': 'Guarda los recibos creados desde las apps de SNG (ruteros y escritorio) '
               'sobre account.payment y agrega un menú para verlos y liquidarlos.',
    'description': """
        Gestión de recibos de pago creados desde las aplicaciones SNG.
        Incluye conciliación, reportes, detección de anomalías y asistencia
        de DeepSeek para matching de facturas, duplicados y morosidad.
    """,
    'version': '18.0.1.8.0',
    'category': 'Accounting',
    'author': 'SNG',
    'website': 'https://sngcloud.com',
    'depends': ['account', 'customer_sequence', 'sales_commission_omax'],
    'data': [
        'security/ir.model.access.csv',
        'data/sng_ia_data.xml',
        'views/account_payment_views.xml',
        'wizard/sng_reporte_pagos_wizard_views.xml',
        'report/sng_reporte_pagos_report.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
