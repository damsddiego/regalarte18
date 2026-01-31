# -*- coding: utf-8 -*-
{
    'name': 'Sale Order Location Selection',
    'version': '18.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Select specific warehouse location for sale orders with stock validation',
    'description': """
Sale Order Location Selection
==============================
This module allows users to select a specific internal warehouse location for each sale order.

Key Features:
* Select internal location for entire sale order
* Validate stock availability at selected location before confirmation
* Block order confirmation if insufficient stock
* Force reservations only from selected location
* Multi-company compatible

The location is set at the sale order level and propagated to pickings and stock moves.
    """,
    'author': 'SNG',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'sale_management',
        'stock',
        'sale_stock_sng',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
