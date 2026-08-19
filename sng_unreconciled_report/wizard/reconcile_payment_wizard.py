# -*- coding: utf-8 -*-
from odoo import fields, models, api
from odoo.exceptions import UserError


class SngReconcileInvoiceLine(models.TransientModel):
    _name = "sng.reconcile.invoice.line"
    _description = "Factura disponible para conciliar"
    _order = "invoice_date_due, invoice_name"

    wizard_id = fields.Many2one("sng.reconcile.payment.wizard", ondelete="cascade")
    move_id = fields.Many2one("account.move", string="Factura", readonly=True)
    invoice_name = fields.Char(string="Número", readonly=True)
    invoice_date = fields.Date(string="Fecha", readonly=True)
    invoice_date_due = fields.Date(string="Vencimiento", readonly=True)
    amount_total = fields.Float(string="Total", digits=(16, 2), readonly=True)
    amount_residual = fields.Float(string="Pendiente", digits=(16, 2), readonly=True)
    currency_name = fields.Char(string="Moneda", readonly=True)
    apply = fields.Boolean(string="Aplicar")


class SngReconcilePaymentWizard(models.TransientModel):
    _name = "sng.reconcile.payment.wizard"
    _description = "Wizard para conciliar un pago con facturas pendientes"

    parent_wizard_id = fields.Many2one("sng.unreconciled.report.wizard")
    payment_id = fields.Many2one("account.payment", readonly=True)
    payment_name = fields.Char(string="Número Pago", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Cliente/Proveedor", readonly=True)
    amount = fields.Float(string="Monto Pago", digits=(16, 2), readonly=True)
    amount_available = fields.Float(string="Disponible", digits=(16, 2), readonly=True)
    currency_id = fields.Many2one("res.currency", string="Moneda", readonly=True)
    date = fields.Date(string="Fecha Pago", readonly=True)
    journal_name = fields.Char(string="Diario", readonly=True)
    invoice_line_ids = fields.One2many(
        "sng.reconcile.invoice.line", "wizard_id", string="Facturas Pendientes"
    )
    amount_to_apply = fields.Float(
        string="Total Seleccionado", compute="_compute_amount_to_apply", digits=(16, 2)
    )

    @api.depends("invoice_line_ids.apply", "invoice_line_ids.amount_residual")
    def _compute_amount_to_apply(self):
        for wiz in self:
            wiz.amount_to_apply = sum(
                l.amount_residual for l in wiz.invoice_line_ids if l.apply
            )

    def action_reconcile(self):
        self.ensure_one()
        selected = self.invoice_line_ids.filtered(lambda l: l.apply)
        if not selected:
            raise UserError("Seleccione al menos una factura para aplicar el pago.")

        payment = self.payment_id
        account_types = ("asset_receivable", "liability_payable")

        payment_ml = payment.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type in account_types and not l.reconciled
        )
        if not payment_ml:
            raise UserError("El pago no tiene saldo pendiente de conciliar.")

        lines_to_reconcile = payment_ml
        for inv_line in selected:
            inv_ml = inv_line.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type in account_types and not l.reconciled
            )
            lines_to_reconcile |= inv_ml

        lines_to_reconcile.reconcile()

        if self.parent_wizard_id:
            self.parent_wizard_id._do_generate()
            return {
                "type": "ir.actions.act_window",
                "res_model": "sng.unreconciled.report.wizard",
                "view_mode": "form",
                "res_id": self.parent_wizard_id.id,
                "target": "current",
            }
        return {"type": "ir.actions.act_window_close"}
