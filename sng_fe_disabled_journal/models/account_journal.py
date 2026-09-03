# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    fe_disabled_journal = fields.Boolean(
        string="Diario sin documentos electrónicos",
        copy=False,
        help="Todas las facturas de este diario se tratan como documentos electrónicos "
        "deshabilitados (no se envían a Hacienda) y conservan la numeración estándar "
        "del diario en lugar de la secuencia de Documentos Desactivados (DA).",
    )
