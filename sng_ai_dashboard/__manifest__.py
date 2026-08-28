# -*- coding: utf-8 -*-
{
    'name': 'SNG AI Dashboard',
    'version': '18.0.1.10.0',
    'category': 'Reporting',
    'summary': 'Dashboard ejecutivo con KPIs y recomendaciones generadas por IA',
    'description': """
        Dashboard para la toma de decisiones con:
        - Ventas del mes (vs mes anterior y mismo mes del año pasado)
        - Ventas por vendedor asignado
        - Segmentación de clientes por compra y salud de pago
        - Morosidad / antigüedad de cuentas por cobrar
        - Valor del inventario por categoría
        - Análisis y recomendaciones generadas con DeepSeek por defecto
        - Compatibilidad opcional con Anthropic
    """,
    'author': 'SNG',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'stock_account',
        'sng_invoice_assigned_salesperson',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/ai_dashboard_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sng_ai_dashboard/static/src/dashboard/**/*',
        ],
    },
    'installable': True,
    'application': True,
}
