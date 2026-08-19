# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    consolidated_payment_auto_reconcile = fields.Boolean(
        string="Conciliar asignaciones consolidadas automaticamente",
        help="Si esta activo, las lineas destino generadas por el pago consolidado "
             "se conciliaran automaticamente contra las facturas seleccionadas dentro "
             "de cada compania.",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    consolidated_payment_auto_reconcile = fields.Boolean(
        related="company_id.consolidated_payment_auto_reconcile",
        readonly=False,
    )
