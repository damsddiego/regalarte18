# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    sng_line_note = fields.Text(string="Nota")

    def write(self, vals):
        res = super().write(vals)
        if "sng_line_note" in vals:
            self._sng_propagate_line_note()
        return res

    def _sng_propagate_line_note(self):
        """Copia la nota de la línea a los movimientos de inventario pendientes.

        Al confirmar la orden la nota se copia en el create del stock.move; si el
        vendedor la edita después (entrega ya creada) hay que reflejarla también.
        Solo se tocan movimientos que todavía no están hechos ni cancelados.
        """
        for line in self:
            note = line.sng_line_note or ""
            moves = line.move_ids.filtered(
                lambda m: m.state not in ("done", "cancel") and (m.sng_line_note or "") != note
            )
            if moves:
                moves.write({"sng_line_note": note})
            move_lines = line.move_ids.move_line_ids.filtered(
                lambda ml: ml.state not in ("done", "cancel") and (ml.sng_line_note or "") != note
            )
            if move_lines:
                move_lines.write({"sng_line_note": note})
