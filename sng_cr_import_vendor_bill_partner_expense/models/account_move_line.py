# -*- coding: utf-8 -*-

from odoo import models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _sng_keeps_stock_interim_account(self):
        """Con valoración automática en esquema anglosajón, la línea de factura de un
        producto almacenable debe quedar en la cuenta puente de compras (entrada de
        existencias). Si se reemplaza por la cuenta del proveedor, esa cuenta puente
        nunca se cierra y la compra se duplica como gasto."""
        self.ensure_one()
        product = self.product_id
        if not product or not self.company_id.anglo_saxon_accounting:
            return False
        if "is_storable" not in product._fields or not product.is_storable:
            return False
        return getattr(product, "valuation", False) == "real_time"

    def _sng_keeps_product_account(self):
        """Líneas cuya cuenta la decide el producto y no el proveedor: mercadería con
        valoración automática y productos de costo en destino (su cuenta de paso se
        concilia contra el asiento del costo en destino)."""
        self.ensure_one()
        if self._sng_keeps_stock_interim_account():
            return True
        product = self.product_id
        return bool(
            product
            and "landed_cost_ok" in product._fields
            and product.landed_cost_ok
        )

    def _sng_partner_expense_account(self):
        """Cuenta de gasto del proveedor que corresponde a esta línea, o vacío.

        Solo aplica a líneas de producto de facturas y notas de crédito de proveedor
        en borrador. Una factura publicada o cancelada nunca se toca."""
        self.ensure_one()
        move = self.move_id
        if move.move_type not in ("in_invoice", "in_refund") or move.state != "draft":
            return self.env["account.account"]
        if self.display_type != "product" or self._sng_keeps_product_account():
            return self.env["account.account"]
        if self.account_id.account_type in ("liability_payable", "asset_receivable"):
            return self.env["account.account"]
        return move.partner_id.with_company(move.company_id).import_bill_expense_account_id

    def _compute_account_id(self):
        # Sin dependencias adicionales a propósito: la cuenta del proveedor es el valor
        # sugerido cuando Odoo calcula la cuenta de una línea (línea nueva o cambio de
        # producto). Cambiar la cuenta en la ficha del proveedor NO recalcula líneas
        # que ya existen; para eso está el botón de la ficha, limitado a borradores.
        super()._compute_account_id()
        for line in self:
            account = line._sng_partner_expense_account()
            if account:
                line.account_id = account
