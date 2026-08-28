# -*- coding: utf-8 -*-
import base64

from markupsafe import Markup
from psycopg2.errors import LockNotAvailable

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from odoo.tools.float_utils import float_compare, float_is_zero


MANAGEMENT_GROUP = "sng_cycle_count.group_cycle_count_management"
SUPERVISOR_GROUP = "sng_cycle_count.group_cycle_count_supervisor"
APPROVAL_ACTIVITY = "sng_cycle_count.mail_activity_cycle_count_approval"
RECOUNT_ACTIVITY = "sng_cycle_count.mail_activity_cycle_count_recount"


class CycleCount(models.Model):
    _name = "sng.cycle.count"
    _description = "Conteo Cíclico"
    _order = "count_date desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Referencia", required=True, copy=False, readonly=True, default="Nuevo")
    count_date = fields.Date(string="Fecha", required=True)
    config_id = fields.Many2one(
        "sng.cycle.count.config",
        string="Configuración",
        required=True,
        ondelete="restrict",
    )
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("in_progress", "En Progreso"),
            ("pending_approval", "Pendiente de Gerencia"),
            ("done", "Finalizado"),
            ("cancelled", "Cancelado"),
        ],
        string="Estado",
        default="draft",
        tracking=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Operador Asignado",
        default=lambda self: self.env.user,
    )
    line_ids = fields.One2many(
        "sng.cycle.count.line",
        "cycle_count_id",
        string="Líneas de Conteo",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        default=lambda self: self.env.company,
        required=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )

    total_lines = fields.Integer(string="Total Líneas", compute="_compute_counts", store=True)
    counted_lines = fields.Integer(string="Líneas Contadas", compute="_compute_counts", store=True)
    discrepancy_lines = fields.Integer(
        string="Líneas con Diferencia",
        compute="_compute_counts",
        store=True,
    )
    has_discrepancies = fields.Boolean(
        string="Tiene Discrepancias",
        compute="_compute_counts",
        store=True,
    )

    total_theoretical_value = fields.Monetary(
        string="Valor Teórico",
        currency_field="currency_id",
        compute="_compute_valuation_totals",
        store=True,
        groups=SUPERVISOR_GROUP,
    )
    total_counted_value = fields.Monetary(
        string="Valor Contado",
        currency_field="currency_id",
        compute="_compute_valuation_totals",
        store=True,
        groups=SUPERVISOR_GROUP,
    )
    total_gain_value = fields.Monetary(
        string="Sobrantes",
        currency_field="currency_id",
        compute="_compute_valuation_totals",
        store=True,
        groups=SUPERVISOR_GROUP,
    )
    total_shortage_value = fields.Monetary(
        string="Faltantes",
        currency_field="currency_id",
        compute="_compute_valuation_totals",
        store=True,
        groups=SUPERVISOR_GROUP,
    )
    total_difference_value = fields.Monetary(
        string="Diferencia Neta",
        currency_field="currency_id",
        compute="_compute_valuation_totals",
        store=True,
        groups=SUPERVISOR_GROUP,
    )

    submitted_by_id = fields.Many2one(
        "res.users",
        string="Finalizado por",
        readonly=True,
        copy=False,
    )
    submitted_at = fields.Datetime(string="Finalizado el", readonly=True, copy=False)
    approved_by_id = fields.Many2one(
        "res.users",
        string="Aprobado por",
        readonly=True,
        copy=False,
    )
    approved_at = fields.Datetime(string="Aprobado el", readonly=True, copy=False)

    @api.depends("line_ids.counted_qty", "line_ids.state", "line_ids.difference_qty")
    def _compute_counts(self):
        for count in self:
            completed_lines = count.line_ids.filtered(
                lambda line: line.state in ("counted", "adjusted")
            )
            discrepancies = completed_lines.filtered(
                lambda line: not float_is_zero(
                    line.difference_qty,
                    precision_rounding=line.product_uom_id.rounding,
                )
            )
            count.total_lines = len(count.line_ids)
            count.counted_lines = len(completed_lines)
            count.discrepancy_lines = len(discrepancies)
            count.has_discrepancies = bool(discrepancies)

    @api.depends(
        "line_ids.theoretical_value",
        "line_ids.counted_value",
        "line_ids.difference_value",
    )
    def _compute_valuation_totals(self):
        for count in self:
            count.total_theoretical_value = sum(count.line_ids.mapped("theoretical_value"))
            count.total_counted_value = sum(count.line_ids.mapped("counted_value"))
            differences = count.line_ids.mapped("difference_value")
            count.total_gain_value = sum(value for value in differences if value > 0.0)
            count.total_shortage_value = abs(sum(value for value in differences if value < 0.0))
            count.total_difference_value = sum(differences)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not self.env.su and vals.get("state", "draft") != "draft":
                raise AccessError(_("Los conteos nuevos deben crearse en borrador."))
            if vals.get("name", "Nuevo") == "Nuevo":
                vals["name"] = self.env["ir.sequence"].next_by_code("sng.cycle.count") or "Nuevo"
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and "state" in vals:
            raise AccessError(_("Utilice las acciones del conteo para cambiar su estado."))

        protected_fields = {"count_date", "config_id", "user_id", "company_id", "line_ids"}
        if not self.env.su and protected_fields.intersection(vals):
            locked_counts = self.filtered(
                lambda count: count.state in ("pending_approval", "done", "cancelled")
            )
            if locked_counts:
                raise UserError(
                    _("No puede modificar un conteo pendiente de aprobación o finalizado.")
                )
        return super().write(vals)

    def _check_management_access(self):
        if not self.env.su and not self.env.user.has_group(MANAGEMENT_GROUP):
            raise AccessError(_("Solo Gerencia de Conteos Cíclicos puede realizar esta acción."))

    def _get_management_users(self):
        self.ensure_one()
        group = self.env.ref(MANAGEMENT_GROUP, raise_if_not_found=False)
        if not group:
            return self.env["res.users"]
        return group.sudo().users.filtered(
            lambda user: user.active
            and not user.share
            and self.company_id in user.company_ids
        )

    def action_start(self):
        for count in self:
            if count.state != "draft":
                raise UserError(_("Solo los conteos en borrador pueden iniciarse."))
            count.sudo().write({"state": "in_progress"})
        return True

    def _refresh_line_unit_costs(self):
        """Refresca el costo unitario de las líneas al costo estándar vigente.

        El costo se fotografía al crear la línea, pero la valoración contable del
        ajuste usa el costo del día de la aprobación; sin este refresco, el reporte
        que ve Gerencia puede diferir del asiento real (o arrastrar costos
        corruptos, caso Peluche Perezoso Roxy 2026-08)."""
        self.ensure_one()
        for line in self.sudo().line_ids.filtered(lambda l: l.state != "cancelled"):
            std = line.product_id.with_company(self.company_id).standard_price
            if abs((line.unit_cost or 0.0) - std) > 0.005:
                line.write({"unit_cost": std})

    def action_submit_for_approval(self):
        for count in self:
            if count.state not in ("draft", "in_progress"):
                raise UserError(
                    _("Solo los conteos en borrador o en progreso pueden finalizarse.")
                )
            if not count.line_ids:
                raise UserError(_("El conteo no contiene líneas."))

            incomplete = count.line_ids.filtered(lambda line: line.state != "counted")
            if incomplete:
                raise UserError(
                    _(
                        "Existen líneas pendientes de conteo. Registre todas las cantidades antes de finalizar."
                    )
                )

            management_users = count._get_management_users()
            if not management_users:
                raise UserError(
                    _(
                        "No hay usuarios activos de Gerencia de Conteos Cíclicos para la compañía %s."
                    )
                    % count.company_id.display_name
                )

            count.sudo().write(
                {
                    "state": "pending_approval",
                    "submitted_by_id": self.env.user.id,
                    "submitted_at": fields.Datetime.now(),
                    "approved_by_id": False,
                    "approved_at": False,
                }
            )
            count._refresh_line_unit_costs()
            count._generate_discrepancy_reports()
            count._notify_management(management_users)
        return True

    def action_approve(self):
        self._check_management_access()
        for count in self:
            if count.state != "pending_approval":
                raise UserError(
                    _("Solo los conteos pendientes de Gerencia pueden aprobarse.")
                )

            count._lock_quants()
            changed_lines = count._get_lines_with_changed_stock()
            if changed_lines:
                product_names = changed_lines.mapped("product_id.display_name")[:10]
                suffix = "" if len(changed_lines) <= 10 else _(" y %s más") % (len(changed_lines) - 10)
                raise UserError(
                    _(
                        "El stock cambió después de capturar el teórico para: %(products)s%(suffix)s. "
                        "Devuelva el conteo para realizar un reconteo antes de aprobar."
                    )
                    % {"products": ", ".join(product_names), "suffix": suffix}
                )

            count._refresh_line_unit_costs()
            counted_lines = count.line_ids.filtered(lambda line: line.state == "counted")
            for line in counted_lines:
                if not float_is_zero(
                    line.difference_qty,
                    precision_rounding=line.product_uom_id.rounding,
                ):
                    line.sudo()._apply_adjustment()

            counted_lines.sudo().write({"state": "adjusted"})
            count.sudo().write(
                {
                    "state": "done",
                    "approved_by_id": self.env.user.id,
                    "approved_at": fields.Datetime.now(),
                }
            )
            count._close_management_activities(
                _("Conteo aprobado por %s.") % self.env.user.display_name
            )
            count.message_post(
                body=Markup("<p>%s</p>")
                % (_("Conteo aprobado y ajustes aplicados por %s.") % self.env.user.display_name),
                subtype_xmlid="mail.mt_note",
            )
        return True

    def action_open_return_wizard(self):
        self.ensure_one()
        self._check_management_access()
        if self.state != "pending_approval":
            raise UserError(_("Solo puede devolver un conteo pendiente de Gerencia."))
        return {
            "name": _("Devolver para reconteo"),
            "type": "ir.actions.act_window",
            "res_model": "sng.cycle.count.return.wizard",
            "view_mode": "form",
            "view_id": self.env.ref("sng_cycle_count.view_cycle_count_return_wizard_form").id,
            "target": "new",
            "context": {"default_cycle_count_id": self.id},
        }

    def action_open_add_product_wizard(self):
        self.ensure_one()
        if self.state not in ("draft", "in_progress"):
            raise UserError(_("Solo puede agregar productos a un conteo en borrador o en progreso."))
        return {
            "name": _("Agregar producto al conteo"),
            "type": "ir.actions.act_window",
            "res_model": "sng.cycle.count.add.product.wizard",
            "view_mode": "form",
            "view_id": self.env.ref("sng_cycle_count.view_cycle_count_add_product_wizard_form").id,
            "target": "new",
            "context": {"default_cycle_count_id": self.id},
        }

    def action_cancel(self):
        for count in self:
            if count.state not in ("draft", "in_progress"):
                raise UserError(
                    _("Solo los conteos en borrador o en progreso pueden cancelarse.")
                )
            count.sudo().write({"state": "cancelled"})
        return True

    def action_reopen(self):
        raise UserError(
            _(
                "Los conteos finalizados son inmutables. Cree un nuevo conteo para realizar correcciones."
            )
        )

    def action_copy_theoretical(self):
        """Copia la cantidad teórica a contada para líneas pendientes."""
        for count in self:
            if count.state not in ("draft", "in_progress"):
                raise UserError(_("El conteo ya no admite cambios."))
            for line in count.line_ids.filtered(lambda item: item.state == "pending"):
                line.write(
                    {
                        "counted_qty": line.theoretical_qty,
                        "state": "counted",
                        "count_date": fields.Datetime.now(),
                    }
                )
        return True

    def _lock_quants(self):
        self.ensure_one()
        quants = self.line_ids.quant_id
        quant_ids = sorted(quants.ids)
        if not quant_ids:
            return
        quants.flush_recordset(["quantity"])
        try:
            with self.env.cr.savepoint(flush=False):
                self.env.cr.execute(
                    "SELECT id FROM stock_quant WHERE id = ANY(%s) ORDER BY id FOR UPDATE NOWAIT",
                    [quant_ids],
                )
        except LockNotAvailable as error:
            raise UserError(
                _("Otro proceso está modificando el inventario. Intente aprobar nuevamente.")
            ) from error
        quants.invalidate_recordset(["quantity"])

    def _get_lines_with_changed_stock(self):
        self.ensure_one()
        return self.line_ids.filtered(
            lambda line: float_compare(
                line.quant_id.quantity,
                line.theoretical_qty,
                precision_rounding=line.product_uom_id.rounding,
            )
            != 0
        )

    def _notify_management(self, management_users):
        self.ensure_one()
        if self.env.ref(APPROVAL_ACTIVITY, raise_if_not_found=False):
            self.sudo().activity_search([APPROVAL_ACTIVITY]).unlink()
            for user in management_users:
                self.sudo().activity_schedule(
                    APPROVAL_ACTIVITY,
                    user_id=user.id,
                    summary=_("Revisar conteo cíclico %s") % self.name,
                    note=_("El conteo fue finalizado y requiere aprobación de Gerencia."),
                )

        self.message_post(
            body=Markup("<p>%s</p>")
            % (_("El conteo %s fue finalizado y está pendiente de revisión gerencial.") % self.name),
            partner_ids=management_users.mapped("partner_id").ids,
            subtype_xmlid="mail.mt_comment",
        )

        template = self.env.ref(
            "sng_cycle_count.email_template_cycle_count_pending_approval",
            raise_if_not_found=False,
        )
        if template:
            for user in management_users.filtered("email"):
                template.sudo().with_context(lang=user.lang or self.env.user.lang).send_mail(
                    self.id,
                    force_send=False,
                    email_values={"email_to": user.email},
                )

    def _close_management_activities(self, feedback):
        self.ensure_one()
        activities = self.sudo().activity_search([APPROVAL_ACTIVITY])
        if activities:
            activities.action_feedback(feedback=feedback)

    def _notify_operator_recount(self, reason, reset_lines, reset_details=None):
        self.ensure_one()
        operator = self.user_id
        self.sudo().activity_search([RECOUNT_ACTIVITY]).unlink()
        if operator and operator.active:
            self.sudo().activity_schedule(
                RECOUNT_ACTIVITY,
                user_id=operator.id,
                summary=_("Recontar %s") % self.name,
                note=reason,
            )

        reset_message = Markup("<p>%s</p>") % _("No fue necesario reiniciar cantidades.")
        if reset_lines:
            reset_message = Markup("<p>%s</p>") % (
                _("Se reiniciaron %s líneas cuyo stock teórico cambió:") % len(reset_lines)
            )
            rows = Markup("").join(
                Markup("<li>%s (%s): teórico %s → %s, contado anterior %s</li>")
                % (
                    d["product"],
                    d["location"],
                    d["old_theo"],
                    d["new_theo"],
                    d["old_counted"],
                )
                for d in (reset_details or [])
            )
            if rows:
                reset_message += Markup("<ul>%s</ul>") % rows
        self.message_post(
            body=Markup("<p><strong>%s</strong></p><p>%s</p>")
            % (_("Conteo devuelto para reconteo"), reason)
            + reset_message,
            partner_ids=operator.partner_id.ids if operator else [],
            subtype_xmlid="mail.mt_comment",
        )

    def _generate_discrepancy_reports(self):
        """Reemplaza los reportes cuantitativos adjuntos con la versión más reciente."""
        self.ensure_one()
        attachment_names = [
            "Discrepancias_%s.pdf" % self.name,
            "Discrepancias_%s.xlsx" % self.name,
        ]
        self.env["ir.attachment"].sudo().search(
            [
                ("res_model", "=", self._name),
                ("res_id", "=", self.id),
                ("name", "in", attachment_names),
            ]
        ).unlink()
        if not self.has_discrepancies:
            return True

        pdf_content, _ = self.env["ir.actions.report"].sudo()._render_qweb_pdf(
            "sng_cycle_count.action_report_cycle_count_discrepancy",
            res_ids=self.ids,
        )
        self.env["ir.attachment"].sudo().create(
            {
                "name": attachment_names[0],
                "type": "binary",
                "datas": base64.b64encode(pdf_content),
                "res_model": self._name,
                "res_id": self.id,
                "mimetype": "application/pdf",
            }
        )

        xlsx_content, _ = self.env["ir.actions.report"].sudo()._render_xlsx(
            "sng_cycle_count.action_report_cycle_count_discrepancy_xlsx",
            self.ids,
            {},
        )
        self.env["ir.attachment"].sudo().create(
            {
                "name": attachment_names[1],
                "type": "binary",
                "datas": base64.b64encode(xlsx_content),
                "res_model": self._name,
                "res_id": self.id,
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
        )
        return True
