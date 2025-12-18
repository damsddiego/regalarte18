# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResPartner(models.Model):
    _inherit = "res.partner"

    sale_location_id = fields.Many2one('stock.location', string="Ubicación de venta", help="Ubicación a utilizar para proceso de venta",
                                       domain=lambda x: [('usage', '=', 'internal')],)

    team_id = fields.Many2one('crm.team', string="Equipo de ventas")
