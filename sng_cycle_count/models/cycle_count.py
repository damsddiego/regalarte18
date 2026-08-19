# -*- coding: utf-8 -*-
import base64
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero


class CycleCount(models.Model):
    _name = "sng.cycle.count"
    _description = "Conteo Cíclico"
    _order = "count_date desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Referencia", required=True, copy=False, readonly=True, default="Nuevo")
    count_date = fields.Date(string="Fecha", required=True)
    config_id = fields.Many2one("sng.cycle.count.config", string="Configuración", required=True, ondelete="restrict")
    state = fields.Selection([
        ("draft", "Borrador"),
        ("in_progress", "En Progreso"),
        ("done", "Validado"),
        ("cancelled", "Cancelado"),
    ], string="Estado", default="draft", tracking=True)
    user_id = fields.Many2one("res.users", string="Operador Asignado", default=lambda self: self.env.user)
    line_ids = fields.One2many("sng.cycle.count.line", "cycle_count_id", string="Líneas de Conteo")
    company_id = fields.Many2one("res.company", string="Compañía", default=lambda self: self.env.company, required=True)

    # Computed
    total_lines = fields.Integer(string="Total Líneas", compute="_compute_counts", store=True)
    counted_lines = fields.Integer(string="Líneas Contadas", compute="_compute_counts", store=True)
    discrepancy_lines = fields.Integer(string="Líneas con Diferencia", compute="_compute_counts", store=True)
    has_discrepancies = fields.Boolean(string="Tiene Discrepancias", compute="_compute_counts", store=True)

    @api.depends("line_ids.counted_qty", "line_ids.state", "line_ids.difference_qty")
    def _compute_counts(self):
        for count in self:
            lines = count.line_ids
            count.total_lines = len(lines)
            count.counted_lines = len(lines.filtered(lambda l: l.state in ("counted", "adjusted")))
            discrepancies = lines.filtered(lambda l: not float_is_zero(l.difference_qty, precision_rounding=l.product_uom_id.rounding))
            count.discrepancy_lines = len(discrepancies)
            count.has_discrepancies = count.discrepancy_lines > 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "Nuevo") == "Nuevo":
                vals["name"] = self.env["ir.sequence"].next_by_code("sng.cycle.count") or "Nuevo"
        return super().create(vals_list)

    def action_start(self):
        for count in self:
            if count.state != "draft":
                raise UserError(_("Solo los conteos en borrador pueden iniciarse."))
            count.state = "in_progress"

    def action_validate(self):
        for count in self:
            if count.state not in ("draft", "in_progress"):
                raise UserError(_("Solo los conteos en borrador o en progreso pueden validarse."))

            # Validar que todas las líneas tengan una cantidad contada
            pending = count.line_ids.filtered(lambda l: l.state == "pending")
            if pending:
                raise UserError(_("Existen líneas pendientes de conteo. Por favor registre todas las cantidades antes de validar."))

            # Aplicar ajustes para líneas con diferencia
            for line in count.line_ids.filtered(lambda l: l.state == "counted" and not float_is_zero(l.difference_qty, precision_rounding=l.product_uom_id.rounding)):
                line._apply_adjustment()
                line.state = "adjusted"
            # Marcar líneas sin diferencia como ajustadas también
            for line in count.line_ids.filtered(lambda l: l.state == "counted" and float_is_zero(l.difference_qty, precision_rounding=l.product_uom_id.rounding)):
                line.state = "adjusted"

            count.state = "done"
            count._generate_discrepancy_reports()

    def action_cancel(self):
        for count in self:
            if count.state == "done":
                raise UserError(_("No puede cancelar un conteo ya validado. Contacte a un supervisor."))
            count.state = "cancelled"

    def action_reopen(self):
        for count in self:
            if count.state != "done":
                raise UserError(_("Solo los conteos validados pueden reabrirse."))
            # No revertimos movimientos de stock ya aplicados; solo reabrimos el registro para seguimiento
            count.state = "in_progress"

    def action_copy_theoretical(self):
        """Copia la cantidad teórica a contada para líneas pendientes."""
        for count in self:
            pending = count.line_ids.filtered(lambda l: l.state == "pending")
            for line in pending:
                line.counted_qty = line.theoretical_qty
                line.state = "counted"
                line.count_date = fields.Datetime.now()

    def _generate_discrepancy_reports(self):
        """Genera y adjunta reportes de discrepancias si las hay."""
        self.ensure_one()
        if not self.has_discrepancies:
            return True

        # PDF
        pdf_content, _ = self.env["ir.actions.report"]._render_qweb_pdf(
            "sng_cycle_count.action_report_cycle_count_discrepancy",
            res_ids=self.ids,
        )
        self.env["ir.attachment"].create({
            "name": "Discrepancias_%s.pdf" % self.name,
            "type": "binary",
            "datas": base64.b64encode(pdf_content),
            "res_model": "sng.cycle.count",
            "res_id": self.id,
            "mimetype": "application/pdf",
        })

        # Excel
        xlsx_content, _ = self.env["ir.actions.report"]._render_xlsx(
            "sng_cycle_count.action_report_cycle_count_discrepancy_xlsx",
            self.ids,
            {},
        )
        self.env["ir.attachment"].create({
            "name": "Discrepancias_%s.xlsx" % self.name,
            "type": "binary",
            "datas": base64.b64encode(xlsx_content),
            "res_model": "sng.cycle.count",
            "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return True
