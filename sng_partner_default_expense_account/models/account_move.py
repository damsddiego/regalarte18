# -*- coding: utf-8 -*-
from odoo import api, fields, models

class AccountMove(models.Model):
    _inherit = "account.move"

    @api.onchange('partner_id', 'move_type')
    def _onchange_partner_expense_account(self):
        """
        Al cambiar el proveedor en una factura de proveedor, asigna la cuenta
        por defecto del proveedor a las líneas sin producto y sin cuenta.
        """
        if self.move_type in ('in_invoice', 'in_refund') and self.partner_id and self.partner_id.property_expense_account_id:
            expense_acc = self.partner_id.property_expense_account_id
            for line in self.invoice_line_ids:
                # Si la línea NO tiene producto y NO tiene cuenta, asignar la cuenta del proveedor
                if not line.product_id and not line.account_id:
                    line.account_id = expense_acc


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.model
    def create(self, vals_list):
        """
        Al crear líneas desde UI, importaciones o API:
        si es una línea de factura de proveedor, sin producto y sin cuenta,
        usar la cuenta de gasto por defecto del proveedor.
        """
        if isinstance(vals_list, dict):
            vals_list = [vals_list]

        # Preprocesar para asignar cuenta si aplica
        for vals in vals_list:
            # Ya viene cuenta explícita o producto: no tocamos
            if vals.get('account_id') or vals.get('product_id'):
                continue

            move_id = vals.get('move_id')
            if not move_id:
                continue

            move = self.env['account.move'].browse(move_id)
            partner = move.partner_id
            if move.move_type in ('in_invoice', 'in_refund') and partner and partner.property_expense_account_id:
                vals['account_id'] = partner.property_expense_account_id.id

        return super().create(vals_list)

    def write(self, vals):
        """
        Si el usuario limpia la cuenta en una línea de factura de proveedor
        que no tiene producto, reponemos la cuenta por defecto del proveedor.
        """
        res = super().write(vals)
        # Solo actuar si potencialmente la cuenta quedó vacía
        if 'account_id' in vals or 'product_id' in vals:
            for line in self:
                if (line.move_id.move_type in ('in_invoice', 'in_refund')
                        and not line.product_id
                        and not line.account_id
                        and line.move_id.partner_id
                        and line.move_id.partner_id.property_expense_account_id):
                    line.account_id = line.move_id.partner_id.property_expense_account_id
        return res
