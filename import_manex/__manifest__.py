# -*- coding: utf-8 -*-
###################################################################################
#    A part of Contigo Project <https://www.manexware.com>
#
#    Manexware S.A.
#    Copyright (C) 2018-TODAY Manexware S.A. (<https://www.manexware.com>).
#    Author: Manuel Vega (<https://www.manexware.com>)
#
#    This program is free software: you can modify
#    it under the terms of the GNU Affero General Public License (AGPL) as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
#    noinspection PyStatementEffect
###################################################################################

{
    'name': "Importaciones Ecuador",

    'summary': """Modulo personalizado de importaciones para Ecuador""",

    'description': """
                       El Módulo Personalizado de Importaciones para Ecuador automatiza la gestión de 
                       costos como fletes, aranceles e impuestos, y ofrece trazabilidad completa de 
                       productos importados. Integra la contabilidad de Odoo, generando transacciones 
                       automáticas para cumplir con normativas fiscales. Ideal para optimizar operaciones 
                       de comercio exterior en Ecuador.
                       """,

    'author': 'Manexware',
    'company': 'Manexware',
    'website': 'https://manexware.com',
    'category': 'Stock',
    "version": "18.0.1.0.1",
    'license': 'LGPL-3',
    'depends': ['stock_landed_costs'],

    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/stock_landed_cost.xml',
        'views/account_move_views.xml',
        'wizard/wizard_landed_cost_view.xml',
        'reports/import_manex_report.xml',
    ],
    "cloc_exclude": [
        "./**/*",
    ],

}
