# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    fe_keep_xml_line_amounts = fields.Boolean(
        string="Mantener montos del XML al cambiar producto",
        help=(
            "En las facturas de este proveedor importadas desde el XML de Hacienda, "
            "al asignar un producto a una línea se conservan el precio unitario, la "
            "cantidad y los impuestos que traía el XML. Útil para agentes aduanales y "
            "transportistas cuyas líneas se cargan como costo en destino."
        ),
    )
