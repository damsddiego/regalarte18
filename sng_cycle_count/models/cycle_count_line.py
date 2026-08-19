# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero, float_compare


class CycleCountLine(models.Model):
    _name = "sng.cycle.count.line"
    _description = "Línea de Conteo Cíclico"
    _order = "cycle_count_id, id"

    cycle_count_id = fields.Many2one("sng.cycle.count", string="Conteo", required=True, ondelete="cascade")
    quant_id = fields.Many2one("stock.quant", string="Quant", required=True, ondelete="restrict")
    product_id = fields.Many2one("product.product", string="Producto", related="quant_id.product_id", store=True)
    product_uom_id = fields.Many2one("uom.uom", string="UdM", related="quant_id.product_uom_id")
    location_id = fields.Many2one("stock.location", string="Ubicación", related="quant_id.location_id", store=True)
    lot_id = fields.Many2one("stock.lot", string="Lote/Serie", related="quant_id.lot_id", store=True)
    package_id = fields.Many2one("stock.quant.package", string="Paquete", related="quant_id.package_id")

    theoretical_qty = fields.Float(string="Cantidad Teórica", digits="Product Unit of Measure", required=True)
    counted_qty = fields.Float(string="Cantidad Contada", digits="Product Unit of Measure", default=0.0)
    difference_qty = fields.Float(string="Diferencia", digits="Product Unit of Measure", compute="_compute_difference", store=True)

    state = fields.Selection([
        ("pending", "Pendiente"),
        ("counted", "Contado"),
        ("adjusted", "Ajustado"),
        ("cancelled", "Cancelado"),
    ], string="Estado", default="pending")
    notes = fields.Text(string="Observaciones")
    count_date = fields.Datetime(string="Fecha de Conteo")
    company_id = fields.Many2one("res.company", string="Compañía", related="cycle_count_id.company_id", store=True)

    @api.depends("theoretical_qty", "counted_qty")
    def _compute_difference(self):
        for line in self:
            line.difference_qty = line.counted_qty - line.theoretical_qty

    @api.onchange("counted_qty")
    def _onchange_counted_qty(self):
        if self.counted_qty < 0:
            self.counted_qty = 0.0
            return {"warning": {"title": _("Cantidad inválida"), "message": _("La cantidad contada no puede ser negativa.")}}
        # Capturar una cantidad marca la línea como contada automáticamente
        if self.state == "pending":
            self.state = "counted"
            self.count_date = fields.Datetime.now()

    def action_set_counted(self):
        for line in self:
            if line.state in ("adjusted", "cancelled"):
                raise UserError(_("No puede modificar una línea ya ajustada o cancelada."))
            line.state = "counted"
            line.count_date = fields.Datetime.now()

    def action_copy_theoretical(self):
        for line in self:
            if line.state in ("adjusted", "cancelled"):
                continue
            line.counted_qty = line.theoretical_qty
            line.state = "counted"
            line.count_date = fields.Datetime.now()

    def _apply_adjustment(self):
        """Aplica el ajuste de inventario en el quant relacionado."""
        self.ensure_one()
        if float_is_zero(self.difference_qty, precision_rounding=self.product_uom_id.rounding):
            return True

        quant = self.quant_id
        # Establecemos la cantidad contada en el quant
        quant.inventory_quantity = self.counted_qty
        # Llamamos al método privado para aplicar el ajuste sin abrir wizards de conflicto
        # Usamos sudo para asegurar permisos de inventario
        quant.sudo()._apply_inventory()
        return True
