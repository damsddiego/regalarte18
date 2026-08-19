# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ConsolidatedCustomerPaymentBridge(models.Model):
    _name = "consolidated.customer.payment.bridge"
    _description = "Configuracion de puente intercompany para pagos consolidados"
    _order = "company_id, counterpart_company_id"
    _rec_name = "display_name"
    _check_company_auto = True

    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compania",
        required=True,
        default=lambda self: self.env.company,
    )
    counterpart_company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compania contraparte",
        required=True,
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Diario de puente",
        required=True,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        check_company=True,
    )
    bridge_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta puente",
        required=True,
        domain="[('deprecated', '=', False), ('account_type', 'in', ('asset_current', 'liability_current')), ('company_id', '=', company_id)]",
        check_company=True,
        ondelete="restrict",
    )
    note = fields.Char(string="Nota")
    display_name = fields.Char(
        compute="_compute_display_name",
        string="Nombre",
    )

    _sql_constraints = [
        (
            "consolidated_customer_payment_bridge_unique",
            "unique(company_id, counterpart_company_id)",
            "La configuracion de puente debe ser unica por par de companias.",
        ),
    ]

    @api.depends("company_id", "counterpart_company_id", "bridge_account_id")
    def _compute_display_name(self):
        for record in self:
            names = [record.company_id.display_name, "->", record.counterpart_company_id.display_name]
            if record.bridge_account_id:
                names.append("(%s)" % record.bridge_account_id.display_name)
            record.display_name = " ".join(filter(None, names))

    @api.constrains("company_id", "counterpart_company_id")
    def _check_companies(self):
        for record in self:
            if record.company_id == record.counterpart_company_id:
                raise ValidationError(_("La compania y la contraparte deben ser distintas."))

    @api.constrains("bridge_account_id")
    def _check_bridge_account(self):
        for record in self:
            if record.bridge_account_id and not record.bridge_account_id.reconcile:
                raise ValidationError(
                    _("La cuenta puente debe ser conciliable para soportar trazabilidad y seguimiento.")
                )
