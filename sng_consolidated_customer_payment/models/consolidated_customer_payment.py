# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError, ValidationError


class ConsolidatedCustomerPayment(models.Model):
    _name = "consolidated.customer.payment"
    _description = "Pago consolidado de clientes"
    _order = "payment_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(
        string="Referencia",
        required=True,
        copy=False,
        default="New",
        readonly=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Borrador"),
            ("confirmed", "Confirmado"),
            ("posted", "Publicado"),
            ("cancelled", "Cancelado"),
        ],
        string="Estado",
        default="draft",
        required=True,
        readonly=True,
        copy=False,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compania receptora",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Moneda",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )
    payment_date = fields.Date(
        string="Fecha de pago",
        required=True,
        default=fields.Date.context_today,
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Diario de recepcion",
        required=True,
        domain="[('type', 'in', ('bank', 'cash', 'credit')), ('company_id', '=', company_id)]",
        check_company=True,
    )
    payment_method_line_id = fields.Many2one(
        comodel_name="account.payment.method.line",
        string="Metodo de pago",
        required=True,
        domain="[('journal_id', '=', journal_id), ('payment_type', '=', 'inbound')]",
        check_company=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Cliente",
        required=True,
        domain="[('parent_id', '=', False)]",
    )
    commercial_partner_id = fields.Many2one(
        comodel_name="res.partner",
        related="partner_id.commercial_partner_id",
        string="Cliente comercial",
        store=True,
        readonly=True,
    )
    amount = fields.Monetary(
        string="Monto recibido",
        currency_field="currency_id",
        required=True,
    )
    memo = fields.Char(string="Memo")
    auto_reconcile = fields.Boolean(
        string="Conciliar automaticamente",
        default=lambda self: self.env.company.consolidated_payment_auto_reconcile,
        help="Si esta activo, el sistema conciliara las lineas generadas contra las "
             "facturas asignadas dentro de cada compania.",
    )
    line_ids = fields.One2many(
        comodel_name="consolidated.customer.payment.line",
        inverse_name="payment_id",
        string="Asignaciones",
        copy=True,
    )
    payment_ids = fields.One2many(
        comodel_name="account.payment",
        inverse_name="consolidated_payment_id",
        string="Pagos generados",
        readonly=True,
    )
    move_ids = fields.One2many(
        comodel_name="account.move",
        inverse_name="consolidated_payment_id",
        string="Asientos generados",
        readonly=True,
    )
    allocated_amount = fields.Monetary(
        string="Monto asignado",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
        readonly=True,
    )
    unallocated_amount = fields.Monetary(
        string="Monto sin asignar",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
        readonly=True,
    )
    line_count = fields.Integer(
        string="Lineas",
        compute="_compute_counts",
        readonly=True,
    )
    payment_count = fields.Integer(
        string="Pagos",
        compute="_compute_counts",
        readonly=True,
    )
    move_count = fields.Integer(
        string="Asientos",
        compute="_compute_counts",
        readonly=True,
    )
    invoice_count = fields.Integer(
        string="Facturas",
        compute="_compute_counts",
        readonly=True,
    )
    reconciliation_count = fields.Integer(
        string="Conciliadas",
        compute="_compute_counts",
        readonly=True,
    )

    @api.depends("line_ids.allocated_amount")
    def _compute_totals(self):
        for record in self:
            record.allocated_amount = sum(record.line_ids.mapped("allocated_amount"))
            record.unallocated_amount = record.amount - record.allocated_amount

    @api.depends("line_ids", "payment_ids", "move_ids", "line_ids.target_move_line_id", "line_ids.target_move_line_id.reconciled")
    def _compute_counts(self):
        for record in self:
            record.line_count = len(record.line_ids)
            record.payment_count = len(record.payment_ids)
            record.move_count = len(record.move_ids)
            record.invoice_count = len(record.line_ids.invoice_move_id)
            record.reconciliation_count = len(record.line_ids.filtered("is_target_reconciled"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("consolidated.customer.payment") or "New"
            journal_id = vals.get("journal_id")
            if journal_id and not vals.get("payment_method_line_id"):
                journal = self.env["account.journal"].browse(journal_id)
                payment_method = self._get_default_inbound_payment_method_line(journal)
                if payment_method:
                    vals["payment_method_line_id"] = payment_method.id
        return super().create(vals_list)

    def write(self, vals):
        protected_fields = set(vals) - {"state"}
        if protected_fields and any(record.state in ("posted", "cancelled") for record in self):
            raise UserError(_("No puedes modificar pagos consolidados publicados o cancelados."))
        return super().write(vals)

    def unlink(self):
        if any(record.state == "posted" for record in self):
            raise UserError(_("No puedes eliminar pagos consolidados publicados."))
        return super().unlink()

    @api.onchange("journal_id")
    def _onchange_journal_id(self):
        if self.journal_id:
            self.payment_method_line_id = self._get_default_inbound_payment_method_line(self.journal_id)

    def _get_default_inbound_payment_method_line(self, journal):
        self.ensure_one() if self else None
        payment_lines = journal.inbound_payment_method_line_ids
        return payment_lines.filtered(lambda line: line.code == "manual")[:1] or payment_lines[:1]

    def _get_default_misc_journal(self, company):
        journal = self.env["account.journal"].with_company(company).search([
            ("company_id", "=", company.id),
            ("type", "=", "general"),
        ], limit=1)
        if not journal:
            raise UserError(
                _("La compania %s no tiene un diario miscelaneo para generar las asignaciones locales.") % company.display_name
            )
        return journal

    def _get_bridge_config(self, company, counterpart_company):
        bridge = self.env["consolidated.customer.payment.bridge"].search([
            ("company_id", "=", company.id),
            ("counterpart_company_id", "=", counterpart_company.id),
            ("active", "=", True),
        ], limit=1)
        if not bridge:
            raise UserError(
                _("Falta configurar el puente intercompany %s -> %s.")
                % (company.display_name, counterpart_company.display_name)
            )
        return bridge

    def _validate_before_confirm(self):
        self.ensure_one()
        if self.amount <= 0.0:
            raise ValidationError(_("El monto recibido debe ser mayor que cero."))
        if self.journal_id.company_id != self.company_id:
            raise ValidationError(_("El diario receptor debe pertenecer a la compania receptora."))
        if self.journal_id.type not in ("bank", "cash", "credit"):
            raise ValidationError(_("El diario receptor debe ser de banco, caja o tarjeta."))
        if self.journal_id.currency_id and self.journal_id.currency_id != self.currency_id:
            raise ValidationError(
                _("La v1 solo soporta pagos en la moneda de la compania. El diario receptor debe usar la misma moneda.")
            )
        if not self.payment_method_line_id:
            raise ValidationError(_("Debes seleccionar un metodo de pago de entrada."))
        if self.payment_method_line_id.journal_id != self.journal_id or self.payment_method_line_id.payment_type != "inbound":
            raise ValidationError(_("El metodo de pago seleccionado no corresponde al diario receptor."))

        allocated_lines = self.line_ids.filtered(lambda line: line.allocated_amount > 0.0)
        if not allocated_lines:
            raise ValidationError(_("Debes asignar al menos una factura con monto mayor que cero."))
        if self.allocated_amount > self.amount:
            raise ValidationError(_("El monto asignado no puede exceder el monto recibido."))

        invoices = self.env["account.move"]
        for line in allocated_lines:
            if line.invoice_move_id in invoices:
                raise ValidationError(_("No puedes asignar la misma factura dos veces."))
            invoices |= line.invoice_move_id

            if line.invoice_move_id.state != "posted":
                raise ValidationError(_("La factura %s debe estar publicada.") % line.invoice_move_id.display_name)
            if line.invoice_move_id.move_type not in ("out_invoice", "out_receipt"):
                raise ValidationError(_("Solo se soportan facturas o recibos de cliente en esta version."))
            if line.invoice_move_id.payment_state == "paid" or line.invoice_move_id.amount_residual <= 0.0:
                raise ValidationError(_("La factura %s ya no tiene saldo abierto.") % line.invoice_move_id.display_name)
            if line.invoice_move_id.commercial_partner_id != self.commercial_partner_id:
                raise ValidationError(
                    _("La factura %s no pertenece al mismo cliente comercial del pago consolidado.")
                    % line.invoice_move_id.display_name
                )
            if line.invoice_move_id.currency_id != self.currency_id:
                raise ValidationError(
                    _("La factura %s tiene una moneda distinta. La v1 solo soporta misma moneda entre companias.")
                    % line.invoice_move_id.display_name
                )
            if line.company_id.currency_id != self.currency_id:
                raise ValidationError(
                    _("La compania %s usa una moneda distinta. La v1 solo soporta companias con misma moneda.")
                    % line.company_id.display_name
                )
            if line.allocated_amount > line.invoice_move_id.amount_residual:
                raise ValidationError(
                    _("La asignacion de %s excede el saldo abierto actual de la factura %s.")
                    % (line.allocated_amount, line.invoice_move_id.display_name)
                )
            line._get_invoice_reconciliation_account()

            if line.company_id != self.company_id:
                self._get_bridge_config(self.company_id, line.company_id)
                self._get_bridge_config(line.company_id, self.company_id)

    def _get_allocated_lines(self):
        self.ensure_one()
        return self.line_ids.filtered(lambda line: line.allocated_amount > 0.0)

    def _group_allocated_lines_by_company(self):
        self.ensure_one()
        grouped = defaultdict(lambda: self.env["consolidated.customer.payment.line"])
        for line in self._get_allocated_lines():
            grouped[line.company_id] |= line
        return grouped

    def _prepare_source_payment_vals(self):
        self.ensure_one()
        receivable_account = self.partner_id.with_company(self.company_id).property_account_receivable_id
        return {
            "date": self.payment_date,
            "amount": self.amount,
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": self.commercial_partner_id.id,
            "journal_id": self.journal_id.id,
            "payment_method_line_id": self.payment_method_line_id.id,
            "currency_id": self.currency_id.id,
            "destination_account_id": receivable_account.id,
            "memo": self.memo or self.name,
            "payment_reference": self.name,
            "consolidated_payment_id": self.id,
        }

    def _create_source_payment(self):
        self.ensure_one()
        payment = self.env["account.payment"].with_company(self.company_id).create(self._prepare_source_payment_vals())
        payment.action_post()
        payment.move_id.write({
            "consolidated_payment_id": self.id,
            "consolidated_payment_role": "receiver_payment",
        })
        return payment

    def _get_payment_counterpart_line(self, payment):
        payment.ensure_one()
        counterpart_line = payment.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable" and line.credit
        )
        if len(counterpart_line) != 1:
            raise UserError(_("No se encontro una unica linea por cobrar en el pago %s.") % payment.display_name)
        return counterpart_line

    def _prepare_receivable_label(self, line):
        self.ensure_one()
        return "%s / %s / %s" % (
            self.name,
            line.company_id.display_name,
            line.invoice_move_id.display_name,
        )

    def _create_local_allocation_move(self, payment_receivable_line, lines):
        self.ensure_one()
        journal = self._get_default_misc_journal(self.company_id)
        move_vals = {
            "date": self.payment_date,
            "ref": "%s / Local" % self.name,
            "journal_id": journal.id,
            "company_id": self.company_id.id,
            "consolidated_payment_id": self.id,
            "consolidated_payment_role": "receiver_local",
            "line_ids": [],
        }
        commands = []
        for line in lines.sorted("id"):
            amount = line.allocated_amount
            label = self._prepare_receivable_label(line)
            source_sequence = line.sequence * 10 + 1
            target_sequence = line.sequence * 10 + 2
            invoice_account = line._get_invoice_reconciliation_account()
            commands.append(Command.create({
                "name": label,
                "partner_id": self.commercial_partner_id.id,
                "account_id": payment_receivable_line.account_id.id,
                "debit": amount,
                "credit": 0.0,
                "sequence": source_sequence,
            }))
            commands.append(Command.create({
                "name": label,
                "partner_id": self.commercial_partner_id.id,
                "account_id": invoice_account.id,
                "debit": 0.0,
                "credit": amount,
                "sequence": target_sequence,
            }))
        move_vals["line_ids"] = commands
        move = self.env["account.move"].with_company(self.company_id).create(move_vals)
        move.action_post()
        updates = []
        for line in lines:
            source_sequence = line.sequence * 10 + 1
            target_sequence = line.sequence * 10 + 2
            source_line = move.line_ids.filtered(lambda aml: aml.sequence == source_sequence and aml.debit)
            target_line = move.line_ids.filtered(lambda aml: aml.sequence == target_sequence and aml.credit)
            updates.append((line, source_line[:1], target_line[:1], move))
        for line, source_line, target_line, move in updates:
            line.write({
                "source_move_id": move.id,
                "target_move_id": move.id,
                "source_move_line_id": source_line.id,
                "target_move_line_id": target_line.id,
            })
        return move

    def _create_receiver_bridge_move(self, payment_receivable_line, company, lines):
        self.ensure_one()
        bridge = self._get_bridge_config(self.company_id, company)
        commands = []
        total = 0.0
        for line in lines.sorted("id"):
            amount = line.allocated_amount
            total += amount
            commands.append(Command.create({
                "name": self._prepare_receivable_label(line),
                "partner_id": self.commercial_partner_id.id,
                "account_id": payment_receivable_line.account_id.id,
                "debit": amount,
                "credit": 0.0,
                "sequence": line.sequence * 10 + 1,
            }))
        commands.append(Command.create({
            "name": "%s / %s / Bridge" % (self.name, company.display_name),
            "account_id": bridge.bridge_account_id.id,
            "debit": 0.0,
            "credit": total,
            "sequence": 9999,
        }))
        move = self.env["account.move"].with_company(self.company_id).create({
            "date": self.payment_date,
            "ref": "%s / %s / Fuente" % (self.name, company.display_name),
            "journal_id": bridge.journal_id.id,
            "company_id": self.company_id.id,
            "consolidated_payment_id": self.id,
            "consolidated_payment_role": "receiver_bridge",
            "line_ids": commands,
        })
        move.action_post()
        for line in lines:
            source_line = move.line_ids.filtered(lambda aml: aml.sequence == line.sequence * 10 + 1 and aml.debit)[:1]
            line.write({
                "source_move_id": move.id,
                "source_move_line_id": source_line.id,
            })
        return move

    def _create_target_bridge_move(self, company, lines):
        self.ensure_one()
        bridge = self._get_bridge_config(company, self.company_id)
        total = sum(lines.mapped("allocated_amount"))
        commands = [Command.create({
            "name": "%s / %s / Bridge" % (self.name, company.display_name),
            "account_id": bridge.bridge_account_id.id,
            "debit": total,
            "credit": 0.0,
            "sequence": 1,
        })]
        for line in lines.sorted("id"):
            commands.append(Command.create({
                "name": self._prepare_receivable_label(line),
                "partner_id": self.commercial_partner_id.id,
                "account_id": line._get_invoice_reconciliation_account().id,
                "debit": 0.0,
                "credit": line.allocated_amount,
                "sequence": line.sequence * 10 + 2,
            }))
        move = self.env["account.move"].with_company(company).create({
            "date": self.payment_date,
            "ref": "%s / %s / Destino" % (self.name, company.display_name),
            "journal_id": bridge.journal_id.id,
            "company_id": company.id,
            "consolidated_payment_id": self.id,
            "consolidated_payment_role": "target_bridge",
            "line_ids": commands,
        })
        move.action_post()
        for line in lines:
            target_line = move.line_ids.filtered(lambda aml: aml.sequence == line.sequence * 10 + 2 and aml.credit)[:1]
            line.write({
                "target_move_id": move.id,
                "target_move_line_id": target_line.id,
            })
        return move

    def _reconcile_payment_with_source_lines(self, payment_line, source_lines):
        to_reconcile = (payment_line + source_lines).filtered(lambda line: not line.reconciled)
        if len(to_reconcile) > 1:
            to_reconcile.reconcile()

    def _reconcile_target_line(self, line):
        invoice_lines = line._get_open_invoice_receivable_lines(include_partially_reconciled=True)
        to_reconcile = (invoice_lines + line.target_move_line_id).filtered(lambda aml: not aml.reconciled)
        if len(to_reconcile) > 1:
            to_reconcile.reconcile()

    def action_load_open_invoices(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Cargar facturas abiertas"),
            "res_model": "consolidated.customer.payment.load.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_payment_id": self.id,
            },
        }

    def action_auto_allocate(self):
        for record in self:
            remaining = record.amount
            commands = []
            ordered_lines = record.line_ids.sorted(
                key=lambda line: (
                    line.invoice_date_due or fields.Date.to_date("2999-12-31"),
                    line.invoice_date or fields.Date.to_date("2999-12-31"),
                    line.company_id.id,
                    line.id,
                )
            )
            for line in ordered_lines:
                allocated = 0.0
                if remaining > 0.0:
                    allocated = min(line.invoice_move_id.amount_residual, remaining)
                remaining -= allocated
                commands.append((line.id, allocated))
            for line_id, allocated in commands:
                self.env["consolidated.customer.payment.line"].browse(line_id).allocated_amount = allocated
        return True

    def action_confirm(self):
        for record in self:
            if record.state != "draft":
                raise UserError(_("Solo puedes confirmar pagos consolidados en borrador."))
            record._validate_before_confirm()
            record.state = "confirmed"
        return True

    def action_reset_to_draft(self):
        for record in self:
            if record.state not in ("confirmed", "cancelled"):
                raise UserError(_("Solo puedes volver a borrador desde confirmado o cancelado."))
            record.state = "draft"
        return True

    def action_cancel(self):
        for record in self:
            if record.state == "posted":
                raise UserError(
                    _("Por seguridad, un pago consolidado publicado no se cancela automaticamente. "
                      "Reversa primero los asientos/pagos nativos y luego registra un nuevo flujo.")
                )
            record.state = "cancelled"
        return True

    def action_post(self):
        for record in self:
            if record.state != "confirmed":
                raise UserError(_("Solo puedes publicar pagos consolidados confirmados."))
            record._validate_before_confirm()
            payment = record._create_source_payment()
            payment_line = record._get_payment_counterpart_line(payment)

            grouped_lines = record._group_allocated_lines_by_company()
            for company, lines in grouped_lines.items():
                if company == record.company_id:
                    record._create_local_allocation_move(payment_line, lines)
                else:
                    record._create_receiver_bridge_move(payment_line, company, lines)
                    record._create_target_bridge_move(company, lines)

                record._reconcile_payment_with_source_lines(payment_line, lines.mapped("source_move_line_id"))
                if record.auto_reconcile:
                    for line in lines:
                        record._reconcile_target_line(line)

            record.state = "posted"
        return True

    def action_open_entries(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Asientos generados"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", self.move_ids.ids)],
            "context": {"create": False},
        }

    def action_open_payments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Pagos generados"),
            "res_model": "account.payment",
            "view_mode": "list,form",
            "domain": [("id", "in", self.payment_ids.ids)],
            "context": {"create": False},
        }

    def action_open_invoices(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Facturas asignadas"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", self.line_ids.invoice_move_id.ids)],
            "context": {"create": False},
        }

    def action_open_reconciliation(self):
        self.ensure_one()
        aml_ids = (
            self.line_ids.source_move_line_id
            + self.line_ids.target_move_line_id
            + self.payment_ids.move_id.line_ids.filtered(lambda line: line.account_id.account_type == "asset_receivable")
        ).ids
        return {
            "type": "ir.actions.act_window",
            "name": _("Lineas para conciliacion"),
            "res_model": "account.move.line",
            "view_mode": "list,form",
            "domain": [("id", "in", aml_ids)],
            "context": {"create": False},
        }


class ConsolidatedCustomerPaymentLine(models.Model):
    _name = "consolidated.customer.payment.line"
    _description = "Linea de pago consolidado"
    _order = "sequence, id"

    payment_id = fields.Many2one(
        comodel_name="consolidated.customer.payment",
        string="Pago consolidado",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compania",
        related="invoice_move_id.company_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Moneda",
        related="invoice_move_id.currency_id",
        store=True,
        readonly=True,
    )
    invoice_move_id = fields.Many2one(
        comodel_name="account.move",
        string="Factura",
        required=True,
        ondelete="restrict",
        domain="[('move_type', 'in', ('out_invoice', 'out_receipt')), ('state', '=', 'posted'), ('payment_state', 'in', ('not_paid', 'partial', 'in_payment')), ('commercial_partner_id', '=', parent.commercial_partner_id), ('currency_id', '=', parent.currency_id)]",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Cliente comercial",
        related="invoice_move_id.commercial_partner_id",
        store=True,
        readonly=True,
    )
    invoice_date = fields.Date(
        string="Fecha factura",
        related="invoice_move_id.invoice_date",
        store=True,
        readonly=True,
    )
    invoice_date_due = fields.Date(
        string="Vencimiento",
        related="invoice_move_id.invoice_date_due",
        store=True,
        readonly=True,
    )
    invoice_payment_state = fields.Selection(
        related="invoice_move_id.payment_state",
        string="Estado de pago",
        store=True,
        readonly=True,
    )
    residual_amount = fields.Monetary(
        string="Saldo actual",
        currency_field="currency_id",
        related="invoice_move_id.amount_residual",
        store=True,
        readonly=True,
    )
    residual_amount_at_load = fields.Monetary(
        string="Saldo cargado",
        currency_field="currency_id",
        readonly=True,
    )
    allocated_amount = fields.Monetary(
        string="Monto asignado",
        currency_field="currency_id",
    )
    source_move_id = fields.Many2one(
        comodel_name="account.move",
        string="Asiento fuente",
        copy=False,
        readonly=True,
        ondelete="set null",
    )
    target_move_id = fields.Many2one(
        comodel_name="account.move",
        string="Asiento destino",
        copy=False,
        readonly=True,
        ondelete="set null",
    )
    source_move_line_id = fields.Many2one(
        comodel_name="account.move.line",
        string="Linea fuente",
        copy=False,
        readonly=True,
        ondelete="set null",
    )
    target_move_line_id = fields.Many2one(
        comodel_name="account.move.line",
        string="Linea destino",
        copy=False,
        readonly=True,
        ondelete="set null",
    )
    is_target_reconciled = fields.Boolean(
        string="Destino conciliado",
        compute="_compute_is_target_reconciled",
        readonly=True,
    )

    @api.depends("target_move_line_id", "target_move_line_id.reconciled", "target_move_line_id.amount_residual")
    def _compute_is_target_reconciled(self):
        for record in self:
            record.is_target_reconciled = bool(record.target_move_line_id) and record.target_move_line_id.reconciled

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("invoice_move_id") and not vals.get("residual_amount_at_load"):
                invoice = self.env["account.move"].browse(vals["invoice_move_id"])
                vals["residual_amount_at_load"] = invoice.amount_residual
        return super().create(vals_list)

    def write(self, vals):
        protected_fields = set(vals) - {
            "source_move_id",
            "target_move_id",
            "source_move_line_id",
            "target_move_line_id",
        }
        if protected_fields and any(line.payment_id.state in ("posted", "cancelled") for line in self):
            raise UserError(_("No puedes modificar lineas de pagos consolidados publicados o cancelados."))
        return super().write(vals)

    def unlink(self):
        if any(line.payment_id.state not in ("draft", "confirmed", "cancelled") for line in self):
            raise UserError(_("No puedes eliminar lineas de un pago consolidado publicado."))
        return super().unlink()

    @api.onchange("invoice_move_id")
    def _onchange_invoice_move_id(self):
        if self.invoice_move_id:
            self.residual_amount_at_load = self.invoice_move_id.amount_residual
            if not self.allocated_amount:
                self.allocated_amount = self.invoice_move_id.amount_residual

    @api.constrains("allocated_amount")
    def _check_allocated_amount(self):
        for line in self:
            if line.allocated_amount < 0.0:
                raise ValidationError(_("El monto asignado no puede ser negativo."))

    def _get_open_invoice_receivable_lines(self, include_partially_reconciled=False):
        self.ensure_one()
        lines = self.invoice_move_id.line_ids.filtered(
            lambda aml: aml.account_id.account_type == "asset_receivable"
            and aml.balance > 0.0
            and (include_partially_reconciled or not aml.reconciled)
            and aml.amount_residual > 0.0
        )
        if not lines:
            raise UserError(_("La factura %s no tiene lineas por cobrar abiertas.") % self.invoice_move_id.display_name)
        return lines

    def _get_invoice_reconciliation_account(self):
        self.ensure_one()
        account = self._get_open_invoice_receivable_lines().account_id
        if len(account) != 1:
            raise UserError(
                _("La factura %s tiene multiples cuentas por cobrar abiertas. Ajusta el documento antes de usar pago consolidado.")
                % self.invoice_move_id.display_name
            )
        return account
