# -*- coding: utf-8 -*-
from odoo import models


class StockQuant(models.Model):
    _inherit = "stock.quant"

    def unlink(self):
        """Odoo borra en bloque los quants en cero (``_unlink_zero_quants``) al
        abrir Disponible o tras movimientos. Las líneas de conteo cíclico apuntan
        al quant con ``ondelete=restrict`` para conservar el historial, lo que
        provocaba un error de FK en toda la pantalla de existencias. Los quants
        referenciados por un conteo se conservan (en cero) y se excluyen del borrado."""
        if not self:
            return super().unlink()
        referenced_ids = {
            group["quant_id"][0]
            for group in self.env["sng.cycle.count.line"]
            .sudo()
            .read_group([("quant_id", "in", self.ids)], ["quant_id"], ["quant_id"])
        }
        if not referenced_ids:
            return super().unlink()
        return super(StockQuant, self - self.browse(list(referenced_ids))).unlink()
