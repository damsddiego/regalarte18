# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    sng_plan_odoo_start_date = fields.Date(
        string='Inicio de Ventas en Odoo',
        help='Primer dia de facturacion real en Odoo. El plan comercial ignora las facturas '
             'con fecha anterior (saldos de CxC cargados desde el sistema anterior) y para '
             'ese tramo usa la venta historica importada.',
    )
