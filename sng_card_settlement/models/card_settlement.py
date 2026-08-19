# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class SngCardSettlement(models.Model):
    _name = "sng.card.settlement"
    _description = "Liquidación de tarjeta"
    _order = "settlement_date desc, id desc"

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
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Banco",
        required=True,
        domain="[('id', 'in', allowed_bank_journal_ids)]",
    )
    allowed_bank_journal_ids = fields.Many2many(
        comodel_name="account.journal",
        string="Bancos permitidos",
        compute="_compute_allowed_config_ids",
    )
    allowed_deduction_account_ids = fields.Many2many(
        comodel_name="account.account",
        string="Cuentas de deducción permitidas",
        compute="_compute_allowed_config_ids",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Moneda",
        compute="_compute_currency_id",
        store=True,
        readonly=True,
    )
    transaction_date = fields.Date(
        string="Fecha de transacción",
        required=True,
    )
    settlement_date = fields.Date(
        string="Fecha de liquidación",
        required=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Borrador"),
            ("posted", "Publicado"),
        ],
        string="Estado",
        default="draft",
        required=True,
        readonly=True,
    )
    payment_ids = fields.One2many(
        comodel_name="account.payment",
        inverse_name="card_settlement_id",
        string="Pagos",
        copy=False,
    )
    deduction_ids = fields.One2many(
        comodel_name="sng.card.settlement.deduction",
        inverse_name="settlement_id",
        string="Deducciones",
        copy=True,
    )
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Asiento contable",
        copy=False,
        readonly=True,
        ondelete="restrict",
    )
    gross_amount = fields.Monetary(
        string="Bruto",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
        readonly=True,
    )
    deduction_amount = fields.Monetary(
        string="Deducciones",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
        readonly=True,
    )
    net_amount = fields.Monetary(
        string="Neto",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
        readonly=True,
    )
    payment_count = fields.Integer(
        string="Pagos",
        compute="_compute_payment_count",
        readonly=True,
    )

    @api.depends("journal_id", "company_id")
    def _compute_currency_id(self):
        for settlement in self:
            settlement.currency_id = settlement.journal_id.currency_id or settlement.company_id.currency_id

    @api.depends("company_id")
    def _compute_allowed_config_ids(self):
        for settlement in self:
            company = settlement.company_id or self.env.company
            settlement.allowed_bank_journal_ids = company.card_settlement_bank_journal_ids
            settlement.allowed_deduction_account_ids = company.card_settlement_deduction_account_ids

    @api.depends("payment_ids", "payment_ids.amount", "deduction_ids.amount")
    def _compute_amounts(self):
        for settlement in self:
            gross_amount = sum(settlement.payment_ids.mapped("amount"))
            deduction_amount = sum(settlement.deduction_ids.mapped("amount"))
            settlement.gross_amount = gross_amount
            settlement.deduction_amount = deduction_amount
            settlement.net_amount = gross_amount - deduction_amount

    @api.depends("payment_ids")
    def _compute_payment_count(self):
        for settlement in self:
            settlement.payment_count = len(settlement.payment_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("sng.card.settlement") or "New"
        return super().create(vals_list)

    def write(self, vals):
        protected_fields = set(vals) - {"state"}
        if protected_fields and any(record.state == "posted" for record in self):
            raise UserError(_("No puedes modificar una liquidación de tarjeta ya publicada."))
        return super().write(vals)

    def unlink(self):
        if any(record.state == "posted" for record in self):
            raise UserError(_("No puedes eliminar una liquidación de tarjeta ya publicada."))
        return super().unlink()

    @api.constrains("journal_id")
    def _check_journal_type(self):
        for settlement in self:
            if settlement.journal_id and settlement.journal_id.type != "bank":
                raise ValidationError(_("La liquidación debe usar un diario bancario."))
            if (
                settlement.journal_id
                and settlement.company_id.card_settlement_bank_journal_ids
                and settlement.journal_id not in settlement.company_id.card_settlement_bank_journal_ids
            ):
                raise ValidationError(_("El banco seleccionado no está configurado para liquidaciones de tarjeta."))

    @api.constrains("gross_amount", "deduction_amount", "net_amount")
    def _check_amounts(self):
        for settlement in self:
            if settlement.currency_id and settlement.net_amount < 0 and not settlement.currency_id.is_zero(settlement.net_amount):
                raise ValidationError(_("El depósito neto no puede ser negativo."))

    def action_post(self):
        for settlement in self:
            settlement._validate_before_post()
            move = self.env["account.move"].create(settlement._prepare_move_vals())
            move.action_post()
            settlement.write({
                "move_id": move.id,
                "state": "posted",
            })
            settlement._reconcile_outstanding_lines()
        return True

    def action_open_move(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_("La liquidación todavía no tiene un asiento contable."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Asiento contable"),
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.move_id.id,
            "target": "current",
        }

    def action_open_payments(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_account_payments")
        action["domain"] = [("id", "in", self.payment_ids.ids)]
        action["context"] = {"create": False}
        return action

    @api.model
    def validate_selected_payments(self, payments, journal, transaction_date, company, currency, settlement=False):
        self._validate_company_card_settlement_config(company, journal)

        if not payments:
            raise UserError(_("Debes seleccionar al menos un pago para liquidar."))

        invalid_payments = payments.filtered(
            lambda payment: (
                payment.payment_type != "inbound"
                or payment.partner_type != "customer"
                or payment.move_id.state != "posted"
                or payment.state not in ("in_process", "paid")
                or not payment.is_card_settlement_required
                or (payment.card_settlement_id and payment.card_settlement_id != settlement)
                or payment.company_id != company
                or payment.date != transaction_date
                or payment.currency_id != currency
                or not payment.outstanding_account_id
                or payment.journal_id not in company.card_settlement_source_journal_ids
                or payment.outstanding_account_id not in company.card_settlement_bridge_account_ids
            )
        )
        if invalid_payments:
            raise UserError(_(
                "Solo se permiten pagos de cliente publicados, pendientes de liquidar, "
                "del diario de tarjeta configurado, de la misma fecha y moneda."
            ))

    @api.model
    def _validate_company_card_settlement_config(self, company, journal=False):
        missing_labels = []
        if not company.card_settlement_source_journal_ids:
            missing_labels.append(_("diarios fuente de tarjeta"))
        if not company.card_settlement_bank_journal_ids:
            missing_labels.append(_("bancos destino"))
        if not company.card_settlement_bridge_account_ids:
            missing_labels.append(_("cuentas puente de tarjeta"))
        if not company.card_settlement_deduction_account_ids:
            missing_labels.append(_("cuentas de deducción"))
        if missing_labels:
            raise UserError(_(
                "Configura primero la liquidación de tarjeta en Ajustes de Contabilidad: %s."
            ) % ", ".join(missing_labels))

        if journal and journal not in company.card_settlement_bank_journal_ids:
            raise UserError(_("El banco seleccionado no está configurado para liquidaciones de tarjeta."))

    def _validate_before_post(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("Solo puedes publicar liquidaciones en borrador."))
        if not self.journal_id.default_account_id:
            raise UserError(_("El diario bancario debe tener una cuenta bancaria por defecto."))

        self.validate_selected_payments(
            self.payment_ids,
            self.journal_id,
            self.transaction_date,
            self.company_id,
            self.currency_id,
            settlement=self,
        )

        if self.currency_id.is_zero(self.gross_amount):
            raise UserError(_("La liquidación no puede tener un monto bruto igual a cero."))

        if self.net_amount < 0 and not self.currency_id.is_zero(self.net_amount):
            raise UserError(_("El depósito neto no puede ser negativo."))

        invalid_deductions = self.deduction_ids.filtered(
            lambda line: not line.account_id or line.amount <= 0.0
        )
        if invalid_deductions:
            raise UserError(_("Todas las deducciones deben tener cuenta contable y monto positivo."))

        invalid_deduction_accounts = self.deduction_ids.filtered(
            lambda line: line.account_id not in self.company_id.card_settlement_deduction_account_ids
        )
        if invalid_deduction_accounts:
            raise UserError(_("Todas las deducciones deben usar cuentas configuradas para liquidaciones de tarjeta."))

    def _build_line_spec(self, name, account, amount, partner=False):
        self.ensure_one()
        balance = self.currency_id._convert(
            amount,
            self.company_id.currency_id,
            self.company_id,
            self.settlement_date,
        )
        return {
            "name": name,
            "account_id": account.id,
            "partner_id": partner.id if partner else False,
            "currency_id": self.currency_id.id,
            "amount_currency": amount,
            "balance": balance,
        }

    def _prepare_move_vals(self):
        self.ensure_one()
        line_specs = []

        if not self.currency_id.is_zero(self.net_amount):
            line_specs.append(
                self._build_line_spec(
                    _("Depósito neto %s") % self.name,
                    self.journal_id.default_account_id,
                    self.net_amount,
                )
            )

        for deduction in self.deduction_ids:
            line_specs.append(
                self._build_line_spec(
                    deduction.name,
                    deduction.account_id,
                    deduction.amount,
                )
            )

        grouped_amounts = defaultdict(float)
        for payment in self.payment_ids:
            grouped_amounts[payment.outstanding_account_id] += payment.amount

        for account, amount in grouped_amounts.items():
            line_specs.append(
                self._build_line_spec(
                    _("Liquidación tarjeta %s") % self.name,
                    account,
                    -amount,
                )
            )

        balance_diff = sum(spec["balance"] for spec in line_specs)
        if line_specs and not self.company_id.currency_id.is_zero(balance_diff):
            line_specs[0]["balance"] -= balance_diff

        line_vals = []
        for spec in line_specs:
            line_vals.append(Command.create({
                "name": spec["name"],
                "account_id": spec["account_id"],
                "partner_id": spec["partner_id"],
                "currency_id": spec["currency_id"],
                "amount_currency": spec["amount_currency"],
                "debit": spec["balance"] if spec["balance"] > 0.0 else 0.0,
                "credit": -spec["balance"] if spec["balance"] < 0.0 else 0.0,
            }))

        return {
            "date": self.settlement_date,
            "journal_id": self.journal_id.id,
            "company_id": self.company_id.id,
            "ref": self.name,
            "line_ids": line_vals,
        }

    def _reconcile_outstanding_lines(self):
        self.ensure_one()
        for account in self.payment_ids.mapped("outstanding_account_id"):
            payment_lines = self.payment_ids.mapped("move_id.line_ids").filtered(
                lambda line: line.account_id == account and not line.reconciled
            )
            settlement_line = self.move_id.line_ids.filtered(
                lambda line: line.account_id == account and line.credit > 0.0 and not line.reconciled
            )[:1]
            if payment_lines and settlement_line:
                (payment_lines + settlement_line).reconcile()


class SngCardSettlementDeduction(models.Model):
    _name = "sng.card.settlement.deduction"
    _description = "Deducción de liquidación de tarjeta"
    _order = "id"

    settlement_id = fields.Many2one(
        comodel_name="sng.card.settlement",
        string="Liquidación",
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="settlement_id.company_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="settlement_id.currency_id",
        store=True,
        readonly=True,
    )
    name = fields.Char(
        string="Concepto",
        required=True,
    )
    account_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta contable",
        required=True,
        domain="[('id', 'in', allowed_deduction_account_ids)]",
        check_company=True,
    )
    allowed_deduction_account_ids = fields.Many2many(
        comodel_name="account.account",
        related="settlement_id.allowed_deduction_account_ids",
        readonly=True,
    )
    amount = fields.Monetary(
        string="Monto",
        currency_field="currency_id",
        required=True,
    )

    @api.constrains("amount")
    def _check_positive_amount(self):
        for line in self:
            if line.amount <= 0.0:
                raise ValidationError(_("Las deducciones deben tener un monto positivo."))
