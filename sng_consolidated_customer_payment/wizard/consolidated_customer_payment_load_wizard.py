# -*- coding: utf-8 -*-

from odoo import fields, models, Command, _
from odoo.exceptions import UserError


class ConsolidatedCustomerPaymentLoadWizard(models.TransientModel):
    _name = "consolidated.customer.payment.load.wizard"
    _description = "Wizard para cargar facturas abiertas en pago consolidado"

    payment_id = fields.Many2one(
        comodel_name="consolidated.customer.payment",
        string="Pago consolidado",
        required=True,
        ondelete="cascade",
    )
    company_ids = fields.Many2many(
        comodel_name="res.company",
        string="Companias a cargar",
        default=lambda self: self.env.user.company_ids,
    )
    only_overdue = fields.Boolean(
        string="Solo vencidas",
        help="Si esta activo, solo se cargaran facturas con vencimiento en o antes de la fecha del pago.",
    )
    clear_existing_lines = fields.Boolean(
        string="Reemplazar lineas actuales",
        default=True,
    )
    auto_allocate = fields.Boolean(
        string="Autoasignar despues de cargar",
        default=True,
    )

    def action_load(self):
        self.ensure_one()
        payment = self.payment_id
        if payment.state != "draft":
            raise UserError(_("Solo puedes cargar facturas sobre pagos consolidados en borrador."))
        if not payment.partner_id:
            raise UserError(_("Selecciona primero el cliente del pago consolidado."))
        if not self.company_ids:
            raise UserError(_("Selecciona al menos una compania para buscar facturas abiertas."))

        domain = [
            ("company_id", "in", self.company_ids.ids),
            ("move_type", "in", ("out_invoice", "out_receipt")),
            ("state", "=", "posted"),
            ("payment_state", "in", ("not_paid", "partial", "in_payment")),
            ("commercial_partner_id", "=", payment.commercial_partner_id.id),
            ("currency_id", "=", payment.currency_id.id),
            ("amount_residual", ">", 0.0),
        ]
        if self.only_overdue:
            domain.append(("invoice_date_due", "<=", payment.payment_date))

        invoices = self.env["account.move"].search(domain, order="invoice_date_due asc, invoice_date asc, id asc")
        if not invoices:
            raise UserError(_("No se encontraron facturas abiertas que coincidan con los criterios seleccionados."))

        commands = []
        if self.clear_existing_lines:
            commands.append(Command.clear())
        existing_invoice_ids = set(payment.line_ids.invoice_move_id.ids)
        next_sequence = max(payment.line_ids.mapped("sequence"), default=0) + 10
        for invoice in invoices:
            if invoice.id in existing_invoice_ids and self.clear_existing_lines:
                continue
            if invoice.id in existing_invoice_ids and not self.clear_existing_lines:
                continue
            commands.append(Command.create({
                "sequence": next_sequence,
                "invoice_move_id": invoice.id,
                "residual_amount_at_load": invoice.amount_residual,
                "allocated_amount": 0.0,
            }))
            next_sequence += 10

        payment.write({"line_ids": commands})
        if self.auto_allocate:
            payment.action_auto_allocate()
        return {"type": "ir.actions.act_window_close"}
