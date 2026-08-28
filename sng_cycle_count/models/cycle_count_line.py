# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_is_zero


SUPERVISOR_GROUP = "sng_cycle_count.group_cycle_count_supervisor"


class CycleCountLine(models.Model):
    _name = "sng.cycle.count.line"
    _description = "Línea de Conteo Cíclico"
    _order = "cycle_count_id, id"
    _sql_constraints = [
        (
            "cycle_count_quant_uniq",
            "unique(cycle_count_id, quant_id)",
            "Un quant solo puede aparecer una vez en el mismo conteo cíclico.",
        )
    ]

    cycle_count_id = fields.Many2one(
        "sng.cycle.count",
        string="Conteo",
        required=True,
        ondelete="cascade",
    )
    quant_id = fields.Many2one("stock.quant", string="Quant", required=True, ondelete="restrict")
    product_id = fields.Many2one(
        "product.product",
        string="Producto",
        related="quant_id.product_id",
        store=True,
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="UdM",
        related="quant_id.product_uom_id",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Ubicación",
        related="quant_id.location_id",
        store=True,
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lote/Serie",
        related="quant_id.lot_id",
        store=True,
    )
    package_id = fields.Many2one(
        "stock.quant.package",
        string="Paquete",
        related="quant_id.package_id",
    )

    theoretical_qty = fields.Float(
        string="Cantidad Teórica",
        digits="Product Unit of Measure",
        required=True,
    )
    counted_qty = fields.Float(
        string="Cantidad Contada",
        digits="Product Unit of Measure",
        default=0.0,
    )
    previous_theoretical_qty = fields.Float(
        string="Teórico Anterior",
        digits="Product Unit of Measure",
        readonly=True,
        copy=False,
        help="Cantidad teórica que tenía la línea antes de que Gerencia devolviera el conteo. "
        "Solo informativo: no interviene en la diferencia, la valorización ni el ajuste.",
    )
    previous_counted_qty = fields.Float(
        string="Contado Anterior",
        digits="Product Unit of Measure",
        readonly=True,
        copy=False,
        help="Cantidad contada antes de que Gerencia devolviera el conteo. "
        "Solo informativo: el ajuste usa únicamente la Cantidad Contada.",
    )
    difference_qty = fields.Float(
        string="Diferencia",
        digits="Product Unit of Measure",
        compute="_compute_values",
        store=True,
    )

    state = fields.Selection(
        [
            ("pending", "Pendiente"),
            ("counted", "Contado"),
            ("adjusted", "Ajustado"),
            ("cancelled", "Cancelado"),
        ],
        string="Estado",
        default="pending",
    )
    notes = fields.Text(string="Observaciones")
    is_manual = fields.Boolean(
        string="Agregado manualmente",
        default=False,
        readonly=True,
        help="Línea agregada por el operador durante el conteo (no seleccionada por la configuración).",
    )
    count_date = fields.Datetime(string="Fecha de Conteo")
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        related="cycle_count_id.company_id",
        store=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )

    unit_cost = fields.Float(
        string="Costo Unitario",
        digits="Product Price",
        readonly=True,
        copy=False,
        groups=SUPERVISOR_GROUP,
    )
    theoretical_value = fields.Monetary(
        string="Valor Teórico",
        currency_field="currency_id",
        compute="_compute_values",
        store=True,
        groups=SUPERVISOR_GROUP,
    )
    counted_value = fields.Monetary(
        string="Valor Contado",
        currency_field="currency_id",
        compute="_compute_values",
        store=True,
        groups=SUPERVISOR_GROUP,
    )
    difference_value = fields.Monetary(
        string="Diferencia Valorizada",
        currency_field="currency_id",
        compute="_compute_values",
        store=True,
        groups=SUPERVISOR_GROUP,
    )

    @api.depends("theoretical_qty", "counted_qty", "unit_cost", "state")
    def _compute_values(self):
        for line in self:
            is_completed = line.state in ("counted", "adjusted")
            is_cancelled = line.state == "cancelled"
            difference_qty = line.counted_qty - line.theoretical_qty if is_completed else 0.0
            line.difference_qty = difference_qty
            line.theoretical_value = 0.0 if is_cancelled else line.theoretical_qty * line.unit_cost
            line.counted_value = line.counted_qty * line.unit_cost if is_completed else 0.0
            line.difference_value = difference_qty * line.unit_cost

    @api.model_create_multi
    def create(self, vals_list):
        Quant = self.env["stock.quant"]
        CycleCount = self.env["sng.cycle.count"]
        seen_pairs = set()
        for vals in vals_list:
            quant = Quant.browse(vals.get("quant_id")).exists()
            count = CycleCount.browse(vals.get("cycle_count_id")).exists()
            if quant and count:
                if not self.env.su and count.state not in ("draft", "in_progress"):
                    raise UserError(
                        _("No puede agregar líneas a un conteo pendiente o finalizado.")
                    )
                if not self.env.su and vals.get("state", "pending") == "adjusted":
                    raise AccessError(
                        _("Solo la aprobación gerencial puede ajustar una línea.")
                    )
                pair = (count.id, quant.id)
                if pair in seen_pairs or self.search_count(
                    [("cycle_count_id", "=", count.id), ("quant_id", "=", quant.id)],
                    limit=1,
                ):
                    raise ValidationError(
                        _("Un quant solo puede aparecer una vez en el mismo conteo cíclico.")
                    )
                seen_pairs.add(pair)
                vals["unit_cost"] = quant.product_id.with_company(
                    count.company_id
                ).standard_price
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            locked_lines = self.filtered(
                lambda line: line.cycle_count_id.state
                in ("pending_approval", "done", "cancelled")
            )
            if locked_lines:
                raise UserError(
                    _("No puede modificar líneas de un conteo pendiente o finalizado.")
                )
            if {
                "cycle_count_id",
                "unit_cost",
                "theoretical_qty",
                "quant_id",
            }.intersection(vals):
                raise AccessError(_("No puede modificar la base teórica o el costo del conteo."))
            if vals.get("state") == "adjusted":
                raise AccessError(_("Solo la aprobación gerencial puede ajustar una línea."))
        return super().write(vals)

    def unlink(self):
        if not self.env.su and any(
            line.cycle_count_id.state in ("pending_approval", "done", "cancelled")
            for line in self
        ):
            raise UserError(_("No puede eliminar líneas de un conteo pendiente o finalizado."))
        return super().unlink()

    @api.onchange("counted_qty")
    def _onchange_counted_qty(self):
        if self.counted_qty < 0:
            self.counted_qty = 0.0
            return {
                "warning": {
                    "title": _("Cantidad inválida"),
                    "message": _("La cantidad contada no puede ser negativa."),
                }
            }
        if self.state == "pending":
            self.state = "counted"
            self.count_date = fields.Datetime.now()

    @api.constrains("counted_qty")
    def _check_counted_qty(self):
        if any(line.counted_qty < 0 for line in self):
            raise ValidationError(_("La cantidad contada no puede ser negativa."))

    def action_set_counted(self):
        for line in self:
            if line.cycle_count_id.state not in ("draft", "in_progress"):
                raise UserError(_("El conteo ya no admite cambios."))
            if line.state in ("adjusted", "cancelled"):
                raise UserError(_("No puede modificar una línea ya ajustada o cancelada."))
            line.write({"state": "counted", "count_date": fields.Datetime.now()})
        return True

    def action_copy_theoretical(self):
        for line in self:
            if line.cycle_count_id.state not in ("draft", "in_progress"):
                raise UserError(_("El conteo ya no admite cambios."))
            if line.state in ("adjusted", "cancelled"):
                continue
            line.write(
                {
                    "counted_qty": line.theoretical_qty,
                    "state": "counted",
                    "count_date": fields.Datetime.now(),
                }
            )
        return True

    def _apply_adjustment(self):
        """Aplica el ajuste de inventario en el quant relacionado."""
        self.ensure_one()
        if float_is_zero(
            self.difference_qty,
            precision_rounding=self.product_uom_id.rounding,
        ):
            return True

        quant = self.quant_id.sudo().with_context(inventory_mode=True)
        quant.inventory_quantity = self.counted_qty
        quant._apply_inventory()
        return True
