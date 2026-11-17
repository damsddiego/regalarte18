# -*- coding: utf-8 -*-

from odoo import _, api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    import_bill_expense_account_id = fields.Many2one(
        "account.account",
        string="Cuenta de Gasto",
        company_dependent=True,
        domain=[
            ("deprecated", "=", False),
            ("account_type", "in", ["expense", "expense_direct_cost", "expense_depreciation"]),
        ],
        help=(
            "Cuenta contable de gasto asignada a este proveedor. Si se define, "
            "las facturas y notas de credito de proveedor nuevas usaran esta "
            "cuenta en sus lineas de producto. Cambiarla no modifica las facturas "
            "que ya existen."
        ),
    )

    def action_apply_import_bill_expense_account_to_drafts(self):
        """Reaplica la cuenta de gasto a las facturas de proveedor en borrador.

        Nunca toca facturas publicadas ni canceladas."""
        self.ensure_one()
        moves = self.env["account.move"].search(
            [
                ("partner_id", "=", self.id),
                ("move_type", "in", ("in_invoice", "in_refund")),
                ("state", "=", "draft"),
                ("company_id", "=", self.env.company.id),
            ]
        )
        lines = moves._apply_partner_import_bill_expense_account()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success" if lines else "info",
                "title": _("Cuenta de gasto del proveedor"),
                "message": _(
                    "Se actualizaron %(lines)s líneas en %(moves)s facturas en borrador.",
                    lines=len(lines),
                    moves=len(lines.move_id),
                ),
                "sticky": False,
            },
        }

    @api.model
    def _migrate_expense_account_id_to_import_bill_expense_account_id(self):
        """Copy values from the deprecated partner expense field when present.

        In Odoo 18, company-dependent fields are stored directly as jsonb
        columns on the model table.
        """
        self.env.cr.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_name = 'res_partner'
               AND column_name IN (
                   'expense_account_id',
                   'import_bill_expense_account_id'
               )
            """
        )
        columns = {row[0] for row in self.env.cr.fetchall()}
        if not {"expense_account_id", "import_bill_expense_account_id"} <= columns:
            return

        self.env.cr.execute(
            """
            UPDATE res_partner
               SET import_bill_expense_account_id = NULLIF(
                   jsonb_strip_nulls(
                       COALESCE(expense_account_id, '{}'::jsonb)
                       || COALESCE(import_bill_expense_account_id, '{}'::jsonb)
                   ),
                   '{}'::jsonb
               )
             WHERE expense_account_id IS NOT NULL
            """
        )
