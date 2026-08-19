# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    card_settlement_source_journal_ids = fields.Many2many(
        comodel_name="account.journal",
        relation="sng_card_settlement_company_source_journal_rel",
        column1="company_id",
        column2="journal_id",
        string="Diarios fuente de tarjeta",
        domain="[('company_id', '=', id)]",
        check_company=True,
        help="Diarios donde se registran originalmente los cobros con tarjeta que deben liquidarse.",
    )
    card_settlement_bank_journal_ids = fields.Many2many(
        comodel_name="account.journal",
        relation="sng_card_settlement_company_bank_journal_rel",
        column1="company_id",
        column2="journal_id",
        string="Bancos destino de liquidación TC",
        domain="[('type', '=', 'bank'), ('company_id', '=', id)]",
        check_company=True,
        help="Diarios bancarios permitidos para registrar el depósito neto de la liquidación.",
    )
    card_settlement_bridge_account_ids = fields.Many2many(
        comodel_name="account.account",
        relation="sng_card_settlement_company_bridge_account_rel",
        column1="company_id",
        column2="account_id",
        string="Cuentas puente de tarjeta",
        domain="[('deprecated', '=', False)]",
        check_company=True,
        help="Cuentas transitorias que se acreditan al liquidar pagos de tarjeta.",
    )
    card_settlement_deduction_account_ids = fields.Many2many(
        comodel_name="account.account",
        relation="sng_card_settlement_company_deduction_account_rel",
        column1="company_id",
        column2="account_id",
        string="Cuentas de deducción TC",
        domain="[('deprecated', '=', False)]",
        check_company=True,
        help="Cuentas permitidas para comisiones, retenciones e impuestos de liquidación TC.",
    )
