# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    # Campos para tipo de cambio personalizado
    sng_use_custom_rate = fields.Boolean(
        string="Usar Tipo de Cambio Personalizado",
        default=False,
        help="Si está marcado, se usará el tipo de cambio personalizado en lugar del oficial",
        tracking=True,
    )

    sng_custom_exchange_rate = fields.Float(
        string="Tipo de Cambio Personalizado",
        digits=(16, 6),
        default=0.0,
        help="Tipo de cambio personalizado expresado en moneda de la compañía por 1 unidad de moneda extranjera (ej: 458.64 CRC por USD)",
        tracking=True,
    )

    sng_official_exchange_rate = fields.Float(
        string="Tipo de Cambio Oficial",
        digits=(16, 6),
        compute="_compute_sng_official_exchange_rate",
        help="Tipo de cambio oficial expresado en moneda de la compañía por 1 unidad de moneda extranjera",
    )

    @api.constrains('sng_use_custom_rate', 'move_type')
    def _check_custom_rate_invoice_only(self):
        """Restricción: solo permitir en facturas de cliente/proveedor."""
        for move in self:
            if move.sng_use_custom_rate and move.move_type not in (
                'in_invoice', 'in_refund', 'in_receipt', 'out_invoice', 'out_refund'
            ):
                raise ValidationError(_(
                    "El tipo de cambio personalizado solo puede usarse en facturas de cliente o proveedor."
                ))

    @api.constrains('sng_use_custom_rate', 'sng_custom_exchange_rate')
    def _check_custom_rate_positive(self):
        """Restricción: el tipo de cambio debe ser positivo."""
        for move in self:
            if move.sng_use_custom_rate and move.sng_custom_exchange_rate <= 0:
                raise ValidationError(_(
                    "El tipo de cambio personalizado debe ser mayor que cero."
                ))

    @api.depends('currency_id', 'company_id', 'invoice_date', 'date')
    def _compute_sng_official_exchange_rate(self):
        for move in self:
            if not move.currency_id or move.currency_id == move.company_id.currency_id:
                move.sng_official_exchange_rate = 1.0
            else:
                date = move.invoice_date or move.date or fields.Date.context_today(move)
                official_rate = move.env['res.currency']._get_conversion_rate(
                    from_currency=move.company_currency_id,
                    to_currency=move.currency_id,
                    company=move.company_id,
                    date=date,
                )
                # Mostrar como "moneda local por unidad extranjera" (ej: 458.64 CRC/USD)
                move.sng_official_exchange_rate = (1.0 / official_rate) if official_rate > 0 else 1.0

    def _sng_get_custom_invoice_currency_rate(self):
        self.ensure_one()
        if self.sng_use_custom_rate and self.sng_custom_exchange_rate > 0:
            return 1.0 / self.sng_custom_exchange_rate
        return False

    def _sng_recompute_custom_rate_invoice_lines(self):
        for move in self:
            if not move.is_invoice(include_receipts=True) or not move.invoice_line_ids:
                continue

            # Reversals and sale-originated invoice lines must keep the copied
            # commercial price. Recomputing price_unit here uses the product
            # catalog price and can make credit notes differ from the invoice.
            lines_to_reprice = move.invoice_line_ids
            if move.reversed_entry_id:
                lines_to_reprice = self.env["account.move.line"]
            elif "sale_line_ids" in self.env["account.move.line"]._fields:
                lines_to_reprice = lines_to_reprice.filtered(lambda line: not line.sale_line_ids)

            if lines_to_reprice:
                lines_to_reprice._compute_price_unit()
            move.invoice_line_ids._compute_totals()
            move.line_ids._compute_currency_rate()
            move._sng_recompute_line_balances()

    @api.depends(
        'currency_id',
        'company_currency_id',
        'company_id',
        'invoice_date',
        'sng_use_custom_rate',
        'sng_custom_exchange_rate',
    )
    def _compute_invoice_currency_rate(self):
        """Override para preservar el tipo de cambio personalizado.

        Odoo recalcula invoice_currency_rate cuando cambian currency_id,
        company_id, invoice_date o los campos SNG. Este método re-aplica
        la tasa personalizada después del cálculo nativo para mantener
        la intención del usuario.
        """
        super()._compute_invoice_currency_rate()
        for move in self:
            custom_rate = move._sng_get_custom_invoice_currency_rate()
            if custom_rate:
                # Guardamos el valor inverso porque Odoo usa este campo como divisor
                move.invoice_currency_rate = custom_rate

    @api.onchange('currency_id', 'company_id')
    def _onchange_currency_reset_custom_rate(self):
        """Resetear tipo de cambio personalizado cuando cambia la moneda o compañía."""
        if self.currency_id == self.company_id.currency_id:
            self.sng_use_custom_rate = False
            self.sng_custom_exchange_rate = 0.0
        elif not self.sng_custom_exchange_rate:
            self.sng_custom_exchange_rate = self.sng_official_exchange_rate

    @api.onchange('sng_use_custom_rate')
    def _onchange_sng_use_custom_rate(self):
        """Actualizar invoice_currency_rate cuando se activa el tipo de cambio personalizado."""
        if self.sng_use_custom_rate:
            if not self.sng_custom_exchange_rate or self.sng_custom_exchange_rate <= 0:
                self.sng_custom_exchange_rate = self.sng_official_exchange_rate
            if self.sng_custom_exchange_rate > 0:
                self.invoice_currency_rate = 1.0 / self.sng_custom_exchange_rate
                self._sng_recompute_custom_rate_invoice_lines()
        else:
            self.invoice_currency_rate = 1.0 / self.sng_official_exchange_rate

    @api.onchange('sng_custom_exchange_rate')
    def _onchange_sng_custom_exchange_rate(self):
        """Actualizar invoice_currency_rate cuando cambia el tipo de cambio personalizado."""
        if self.sng_use_custom_rate and self.sng_custom_exchange_rate > 0:
            self.invoice_currency_rate = 1.0 / self.sng_custom_exchange_rate
            self._sng_recompute_custom_rate_invoice_lines()

    @api.model_create_multi
    def create(self, vals_list):
        """Al crear, aplicar el tipo de cambio personalizado si está activo."""
        for vals in vals_list:
            if vals.get('sng_use_custom_rate') and vals.get('sng_custom_exchange_rate', 0) > 0:
                vals['invoice_currency_rate'] = 1.0 / vals['sng_custom_exchange_rate']
        moves = super().create(vals_list)
        for move in moves:
            custom_rate = move._sng_get_custom_invoice_currency_rate()
            if custom_rate:
                move.invoice_currency_rate = custom_rate
                if move.is_invoice(include_receipts=True) and move.invoice_line_ids:
                    move._sng_recompute_custom_rate_invoice_lines()
        return moves

    def _reverse_moves(self, default_values_list=None, cancel=False):
        default_values_list = [dict(values or {}) for values in (default_values_list or [{} for _move in self])]
        for move, default_values in zip(self, default_values_list):
            if not move.is_invoice(include_receipts=True):
                continue
            if move.currency_id and move.currency_id != move.company_currency_id and move.invoice_currency_rate:
                default_values.setdefault("invoice_currency_rate", move.invoice_currency_rate)
            if move.sng_use_custom_rate and move.sng_custom_exchange_rate > 0:
                default_values.setdefault("sng_use_custom_rate", True)
                default_values.setdefault("sng_custom_exchange_rate", move.sng_custom_exchange_rate)

        return super()._reverse_moves(default_values_list=default_values_list, cancel=cancel)

    def write(self, vals):
        """Al escribir, aplicar el tipo de cambio personalizado si cambia."""
        if 'sng_use_custom_rate' in vals or 'sng_custom_exchange_rate' in vals:
            if any(m.state != 'draft' for m in self):
                raise UserError(_("No se puede modificar el tipo de cambio de una factura ya confirmada."))
            # Escribir registro por registro para evitar sobrescribir vals en loop
            for move in self:
                move_vals = dict(vals)
                use_custom = move_vals.get('sng_use_custom_rate', move.sng_use_custom_rate)
                custom_rate = move_vals.get('sng_custom_exchange_rate', move.sng_custom_exchange_rate)

                if use_custom and custom_rate > 0:
                    move_vals['invoice_currency_rate'] = 1.0 / custom_rate
                elif not use_custom:
                    move_vals['invoice_currency_rate'] = 1.0 / move.sng_official_exchange_rate

                super(AccountMove, move).write(move_vals)

            # Recalcular balances de líneas existentes si cambió el tipo de cambio
            for move in self:
                if move.is_invoice(include_receipts=True) and move.invoice_line_ids:
                    move._sng_recompute_custom_rate_invoice_lines()
            return True

        return super().write(vals)

    def _sng_recompute_line_balances(self):
        """Recalcular los balances de las líneas cuando cambia el tipo de cambio.

        Odoo protege currency_rate durante el write de account.move, por lo que
        _sync_invoice no detecta el cambio. Este método fuerza el recálculo manual.
        """
        self.ensure_one()
        if not self.is_invoice(include_receipts=True):
            return

        total_balance = 0.0
        payment_term_line = self.env['account.move.line']

        for line in self.line_ids:
            if line.display_type == 'payment_term':
                payment_term_line = line
                continue
            if line.display_type in ('line_section', 'line_note'):
                continue
            if line.currency_rate:
                new_balance = line.company_currency_id.round(line.amount_currency / line.currency_rate)
                line.write({'balance': new_balance})
                total_balance += new_balance
            else:
                total_balance += line.balance

        if payment_term_line:
            payment_term_line.write({'balance': -total_balance})


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _sng_get_custom_price_unit(self):
        self.ensure_one()
        move = self.move_id
        product = self.product_id
        company = move.company_id

        if (
            not product
            or not move.sng_use_custom_rate
            or move.sng_custom_exchange_rate <= 0
            or not move.is_sale_document(include_receipts=True)
            or move.currency_id == company.currency_id
            or product.currency_id != company.currency_id
            or self.sale_line_ids
        ):
            return False

        product_uom = self.product_uom_id or product.uom_id
        product_price_unit = product.with_company(company).lst_price
        product_taxes = product.taxes_id.filtered(lambda tax: tax.company_id == company)

        if product_uom and product.uom_id != product_uom:
            product_price_unit = product.uom_id._compute_price(product_price_unit, product_uom)

        if product_taxes and move.fiscal_position_id:
            product_price_unit = product._get_tax_included_unit_price_from_price(
                product_price_unit,
                product_taxes,
                fiscal_position=move.fiscal_position_id,
            )

        return product_price_unit / move.sng_custom_exchange_rate

    @api.depends(
        'product_id',
        'product_uom_id',
        'move_id.sng_use_custom_rate',
        'move_id.sng_custom_exchange_rate',
        'move_id.currency_id',
        'move_id.company_id',
        'move_id.fiscal_position_id',
    )
    def _compute_price_unit(self):
        super()._compute_price_unit()
        for line in self:
            custom_price = line._sng_get_custom_price_unit()
            if custom_price is not False:
                line.price_unit = custom_price
