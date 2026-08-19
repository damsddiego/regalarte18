# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class SngCardSettlementWizard(models.TransientModel):
    _name = "sng.card.settlement.wizard"
    _description = "Wizard de liquidación de tarjeta"

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
    eligible_payment_ids = fields.Many2many(
        comodel_name="account.payment",
        string="Pagos elegibles",
        compute="_compute_eligible_payment_ids",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Moneda",
        compute="_compute_currency_id",
        readonly=True,
    )
    transaction_date = fields.Date(
        string="Fecha de transacción",
        required=True,
        default=lambda self: fields.Date.context_today(self) - timedelta(days=1),
    )
    settlement_date = fields.Date(
        string="Fecha de liquidación",
        required=True,
        default=fields.Date.context_today,
    )
    payment_ids = fields.Many2many(
        comodel_name="account.payment",
        relation="sng_card_settlement_wizard_payment_rel",
        column1="wizard_id",
        column2="payment_id",
        string="Pagos",
        domain="[('id', 'in', eligible_payment_ids)]",
    )
    deduction_ids = fields.One2many(
        comodel_name="sng.card.settlement.wizard.deduction",
        inverse_name="wizard_id",
        string="Deducciones",
    )
    gross_amount = fields.Monetary(
        string="Bruto",
        currency_field="currency_id",
        compute="_compute_amounts",
        readonly=True,
    )
    deduction_amount = fields.Monetary(
        string="Deducciones",
        currency_field="currency_id",
        compute="_compute_amounts",
        readonly=True,
    )
    net_amount = fields.Monetary(
        string="Neto",
        currency_field="currency_id",
        compute="_compute_amounts",
        readonly=True,
    )

    @api.depends("journal_id", "company_id")
    def _compute_currency_id(self):
        for wizard in self:
            wizard.currency_id = wizard.journal_id.currency_id or wizard.company_id.currency_id

    @api.depends("company_id")
    def _compute_allowed_config_ids(self):
        for wizard in self:
            company = wizard.company_id or self.env.company
            wizard.allowed_bank_journal_ids = company.card_settlement_bank_journal_ids
            wizard.allowed_deduction_account_ids = company.card_settlement_deduction_account_ids

    @api.depends("company_id", "journal_id", "transaction_date")
    def _compute_eligible_payment_ids(self):
        for wizard in self:
            wizard.eligible_payment_ids = wizard._get_eligible_payments()

    @api.depends("payment_ids", "payment_ids.amount", "deduction_ids.amount")
    def _compute_amounts(self):
        for wizard in self:
            wizard.gross_amount = sum(wizard.payment_ids.mapped("amount"))
            wizard.deduction_amount = sum(wizard.deduction_ids.mapped("amount"))
            wizard.net_amount = wizard.gross_amount - wizard.deduction_amount

    @api.onchange("settlement_date")
    def _onchange_settlement_date(self):
        for wizard in self:
            if wizard.settlement_date:
                wizard.transaction_date = wizard.settlement_date - timedelta(days=1)

    @api.onchange("journal_id", "transaction_date", "company_id")
    def _onchange_proposal_fields(self):
        for wizard in self:
            eligible_payments = wizard._get_eligible_payments()
            wizard.eligible_payment_ids = eligible_payments
            wizard.payment_ids = [Command.set(eligible_payments.ids)] if wizard.journal_id and wizard.transaction_date else [Command.clear()]

    def _get_eligible_payments(self):
        self.ensure_one()
        if not self.journal_id or not self.transaction_date:
            return self.env["account.payment"]
        if (
            not self.company_id.card_settlement_source_journal_ids
            or not self.company_id.card_settlement_bank_journal_ids
            or not self.company_id.card_settlement_bridge_account_ids
            or self.journal_id not in self.company_id.card_settlement_bank_journal_ids
        ):
            return self.env["account.payment"]

        currency = self.journal_id.currency_id or self.company_id.currency_id
        return self.env["account.payment"].search([
            ("company_id", "=", self.company_id.id),
            ("journal_id", "in", self.company_id.card_settlement_source_journal_ids.ids),
            ("date", "=", self.transaction_date),
            ("payment_type", "=", "inbound"),
            ("partner_type", "=", "customer"),
            ("move_id.state", "=", "posted"),
            ("state", "in", ("in_process", "paid")),
            ("currency_id", "=", currency.id),
            ("is_card_settlement_required", "=", True),
            ("card_settlement_id", "=", False),
            ("outstanding_account_id", "in", self.company_id.card_settlement_bridge_account_ids.ids),
        ])

    def action_generate_settlement(self):
        self.ensure_one()
        if not self.payment_ids:
            raise UserError(_("No hay pagos seleccionados para liquidar."))
        if self.net_amount < 0:
            raise UserError(_("El depósito neto no puede ser negativo."))

        settlement = self.env["sng.card.settlement"].create({
            "company_id": self.company_id.id,
            "journal_id": self.journal_id.id,
            "transaction_date": self.transaction_date,
            "settlement_date": self.settlement_date,
            "deduction_ids": [
                Command.create({
                    "name": line.name,
                    "account_id": line.account_id.id,
                    "amount": line.amount,
                })
                for line in self.deduction_ids
            ],
        })
        self.env["sng.card.settlement"].validate_selected_payments(
            self.payment_ids,
            self.journal_id,
            self.transaction_date,
            self.company_id,
            settlement.currency_id,
        )
        self.payment_ids.write({"card_settlement_id": settlement.id})
        settlement.action_post()
        return {
            "type": "ir.actions.act_window",
            "name": _("Liquidación de tarjeta"),
            "res_model": "sng.card.settlement",
            "view_mode": "form",
            "res_id": settlement.id,
            "target": "current",
        }


class SngCardSettlementWizardDeduction(models.TransientModel):
    _name = "sng.card.settlement.wizard.deduction"
    _description = "Deducción temporal de liquidación de tarjeta"
    _order = "id"

    wizard_id = fields.Many2one(
        comodel_name="sng.card.settlement.wizard",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="wizard_id.company_id",
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="wizard_id.currency_id",
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
        related="wizard_id.allowed_deduction_account_ids",
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
