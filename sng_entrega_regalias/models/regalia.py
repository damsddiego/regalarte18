# -*- coding: utf-8 -*-

from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class SngRegalia(models.Model):
    _name = "sng.regalia"
    _description = "Entrega de regalías a clientes"
    _order = "date desc, id desc"

    name = fields.Char(
        string="Referencia",
        required=True,
        copy=False,
        default="New",
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Cliente",
        required=True,
    )
    warehouse_id = fields.Many2one(
        comodel_name="stock.warehouse",
        string="Almacén",
        required=True,
        check_company=True,
        default=lambda self: self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        ),
    )
    date = fields.Date(
        string="Fecha",
        required=True,
        default=fields.Date.context_today,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Creado por",
        default=lambda self: self.env.user,
        readonly=True,
    )
    notes = fields.Text(string="Notas")
    line_ids = fields.One2many(
        comodel_name="sng.regalia.line",
        inverse_name="regalia_id",
        string="Líneas",
        copy=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Borrador"),
            ("done", "Entregado"),
            ("cancel", "Cancelado"),
        ],
        string="Estado",
        default="draft",
        required=True,
        readonly=True,
        copy=False,
    )
    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Transferencia",
        copy=False,
        readonly=True,
        ondelete="restrict",
    )
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Asiento contable",
        copy=False,
        readonly=True,
        ondelete="restrict",
    )
    amount_total = fields.Monetary(
        string="Costo total",
        currency_field="currency_id",
        compute="_compute_amount_total",
        store=True,
        readonly=True,
    )

    @api.depends("line_ids.subtotal")
    def _compute_amount_total(self):
        for regalia in self:
            regalia.amount_total = sum(regalia.line_ids.mapped("subtotal"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("sng.regalia") or "New"
        return super().create(vals_list)

    def write(self, vals):
        protected_fields = set(vals) - {"state"}
        if protected_fields and any(record.state == "done" for record in self):
            raise UserError(_("No puedes modificar una regalía ya entregada."))
        return super().write(vals)

    def unlink(self):
        if any(record.state == "done" for record in self):
            raise UserError(_("No puedes eliminar una regalía ya entregada."))
        return super().unlink()

    def action_validate(self):
        if not self.env.user.has_group("sng_entrega_regalias.group_regalia_manager"):
            raise UserError(_("Solo el Responsable de regalías puede validar entregas."))
        for regalia in self:
            regalia._validate_before_post()
            regalia.line_ids._update_cost_from_product()
            picking = regalia._create_and_validate_picking()
            move = self.env["account.move"].with_company(regalia.company_id).create(
                regalia._prepare_move_vals()
            )
            move.action_post()
            regalia.write({
                "picking_id": picking.id,
                "move_id": move.id,
                "state": "done",
            })
        return True

    def action_cancel(self):
        if any(record.state != "draft" for record in self):
            raise UserError(_("Solo puedes cancelar regalías en borrador."))
        self.write({"state": "cancel"})
        return True

    def action_draft(self):
        if any(record.state != "cancel" for record in self):
            raise UserError(_("Solo puedes reestablecer regalías canceladas."))
        self.write({"state": "draft"})
        return True

    def action_open_picking(self):
        self.ensure_one()
        if not self.picking_id:
            raise UserError(_("La regalía todavía no tiene una transferencia."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Transferencia"),
            "res_model": "stock.picking",
            "view_mode": "form",
            "res_id": self.picking_id.id,
            "target": "current",
        }

    def action_open_move(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_("La regalía todavía no tiene un asiento contable."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Asiento contable"),
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.move_id.id,
            "target": "current",
        }

    def _validate_before_post(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("Solo puedes validar regalías en borrador."))
        if not self.line_ids:
            raise UserError(_("La regalía debe tener al menos una línea de producto."))

        invalid_lines = self.line_ids.filtered(lambda line: line.quantity <= 0.0)
        if invalid_lines:
            raise UserError(_("Todas las líneas deben tener una cantidad mayor que cero."))

        non_storable = self.line_ids.filtered(lambda line: not line.product_id.is_storable)
        if non_storable:
            raise UserError(_(
                "Solo se pueden regalar productos almacenables: %s."
            ) % ", ".join(non_storable.mapped("product_id.display_name")))

        self._validate_company_regalia_config(self.company_id)

    @api.model
    def _validate_company_regalia_config(self, company):
        missing_labels = []
        if not company.regalia_expense_account_id:
            missing_labels.append(_("cuenta de gasto de regalías"))
        if not company.regalia_counterpart_account_id:
            missing_labels.append(_("cuenta contrapartida de inventario"))
        if missing_labels:
            raise UserError(_(
                "Configura primero las regalías en Ajustes de Contabilidad: %s."
            ) % ", ".join(missing_labels))

    def _get_default_misc_journal(self, company):
        journal = self.env["account.journal"].with_company(company).search([
            ("company_id", "=", company.id),
            ("type", "=", "general"),
        ], limit=1)
        if not journal:
            raise UserError(
                _("La compañía %s no tiene un diario misceláneo para registrar regalías.") % company.display_name
            )
        return journal

    def _create_and_validate_picking(self):
        self.ensure_one()
        picking_type = self.env.ref("sng_entrega_regalias.picking_type_regalia")
        location_src = self.warehouse_id.lot_stock_id
        location_dest = (
            self.partner_id.with_company(self.company_id).property_stock_customer
            or self.env.ref("stock.stock_location_customers")
        )

        move_commands = []
        for line in self.line_ids:
            move_commands.append(Command.create({
                "name": line.product_id.display_name,
                "product_id": line.product_id.id,
                "product_uom_qty": line.quantity,
                "product_uom": line.product_uom_id.id,
                "location_id": location_src.id,
                "location_dest_id": location_dest.id,
                "picking_type_id": picking_type.id,
                "company_id": self.company_id.id,
            }))

        picking = self.env["stock.picking"].with_company(self.company_id).create({
            "picking_type_id": picking_type.id,
            "partner_id": self.partner_id.id,
            "origin": self.name,
            "company_id": self.company_id.id,
            "location_id": location_src.id,
            "location_dest_id": location_dest.id,
            "move_ids": move_commands,
        })
        picking.action_confirm()
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.with_context(skip_backorder=True, skip_sms=True).button_validate()
        if picking.state != "done":
            raise UserError(_("No se pudo validar la transferencia de la regalía %s.") % self.name)
        return picking

    def _prepare_move_vals(self):
        self.ensure_one()
        company = self.company_id
        currency = company.currency_id
        expense_account = company.regalia_expense_account_id
        counterpart_account = company.regalia_counterpart_account_id
        journal = company.regalia_journal_id or self._get_default_misc_journal(company)

        commands = []
        total = 0.0
        for line in self.line_ids:
            amount = currency.round(line.quantity * line.cost_unit)
            total += amount
            commands.append(Command.create({
                "name": _("Regalía %(name)s - %(product)s") % {
                    "name": self.name,
                    "product": line.product_id.display_name,
                },
                "partner_id": self.partner_id.id,
                "account_id": expense_account.id,
                "debit": amount,
                "credit": 0.0,
            }))
        commands.append(Command.create({
            "name": _("Regalía %s") % self.name,
            "partner_id": self.partner_id.id,
            "account_id": counterpart_account.id,
            "debit": 0.0,
            "credit": total,
        }))

        return {
            "date": self.date,
            "journal_id": journal.id,
            "company_id": company.id,
            "ref": self.name,
            "line_ids": commands,
        }

    def _get_regalia_report_values(self):
        self.ensure_one()
        lines = []
        total_qty = 0.0
        for line in self.line_ids:
            total_qty += line.quantity
            lines.append({
                "code": line.product_id.default_code or "",
                "product": line.product_id.name,
                "quantity": self._format_report_qty(line.quantity),
                "uom": line.product_uom_id.name or "",
            })
        return {
            "lines": lines,
            "totals": {"quantity": self._format_report_qty(total_qty)},
        }

    @api.model
    def _format_report_qty(self, qty):
        if float(qty).is_integer():
            return "%d" % int(qty)
        return "%.2f" % qty


class SngRegaliaLine(models.Model):
    _name = "sng.regalia.line"
    _description = "Línea de regalía"
    _order = "id"

    regalia_id = fields.Many2one(
        comodel_name="sng.regalia",
        string="Regalía",
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="regalia_id.company_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="regalia_id.currency_id",
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Producto",
        required=True,
        domain="[('is_storable', '=', True)]",
        check_company=True,
    )
    quantity = fields.Float(
        string="Cantidad",
        digits="Product Unit of Measure",
        default=1.0,
        required=True,
    )
    product_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        related="product_id.uom_id",
        string="Unidad",
        readonly=True,
    )
    cost_unit = fields.Monetary(
        string="Costo unitario",
        currency_field="currency_id",
        compute="_compute_cost_unit",
        store=True,
        readonly=True,
        help="Costo promedio del producto. Se congela al validar la regalía.",
    )
    subtotal = fields.Monetary(
        string="Subtotal",
        currency_field="currency_id",
        compute="_compute_subtotal",
        store=True,
        readonly=True,
    )

    @api.depends("product_id", "company_id")
    def _compute_cost_unit(self):
        for line in self:
            if line.product_id:
                company = line.company_id or self.env.company
                line.cost_unit = line.product_id.with_company(company).standard_price
            else:
                line.cost_unit = 0.0

    @api.depends("quantity", "cost_unit")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.cost_unit

    @api.constrains("quantity")
    def _check_positive_quantity(self):
        for line in self:
            if line.quantity <= 0.0:
                raise ValidationError(_("Las líneas de regalía deben tener una cantidad mayor que cero."))

    def _update_cost_from_product(self):
        for line in self:
            line.cost_unit = line.product_id.with_company(line.regalia_id.company_id).standard_price

    def write(self, vals):
        if any(line.regalia_id.state == "done" for line in self) and set(vals) - {"cost_unit"}:
            raise UserError(_("No puedes modificar líneas de una regalía ya entregada."))
        return super().write(vals)

    def unlink(self):
        if any(line.regalia_id.state == "done" for line in self):
            raise UserError(_("No puedes eliminar líneas de una regalía ya entregada."))
        return super().unlink()
