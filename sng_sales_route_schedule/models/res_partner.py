# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    sng_cerrado_temporada = fields.Boolean(
        string='Cerrado por temporada',
        tracking=True,
        help='Cliente cerrado temporalmente (temporada verde): no se espera '
             'su visita en el cronograma ni cuenta como incumplimiento.',
    )
