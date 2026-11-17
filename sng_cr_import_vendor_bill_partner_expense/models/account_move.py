# -*- coding: utf-8 -*-

from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _apply_partner_import_bill_expense_account(self):
        """Pone la cuenta de gasto del proveedor en las líneas de producto de las
        facturas en borrador. Devuelve las líneas modificadas."""
        changed = self.env["account.move.line"]
        for move in self:
            for line in move.invoice_line_ids:
                account = line._sng_partner_expense_account()
                if account and line.account_id != account:
                    line.account_id = account
                    changed |= line
        return changed

    def write(self, vals):
        result = super().write(vals)
        # Solo al cambiar de proveedor o de tipo de documento se vuelve a sugerir la
        # cuenta. Agregar o editar líneas no pisa lo que el usuario haya corregido:
        # las líneas nuevas toman la cuenta al calcularse.
        if {"partner_id", "move_type"} & set(vals):
            self._apply_partner_import_bill_expense_account()
        return result

    def load_xml_data(self):
        result = super().load_xml_data()
        # Las líneas cargadas del XML llegan con la cuenta por defecto del diario.
        self._apply_partner_import_bill_expense_account()
        return result
