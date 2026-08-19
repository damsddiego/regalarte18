# -*- coding: utf-8 -*-
import re
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    suggested_payment_id = fields.Many2one(
        comodel_name="account.payment",
        string="Pago Sugerido",
        index=True,
        help="Pago de cliente sugerido para esta línea de extracto (solo informativo).",
    )
    fake_reconcile_state = fields.Selection(
        selection=[
            ("pending", "Pendiente"),
            ("suggested", "Sugerido"),
            ("confirmed", "Confirmado"),
            ("ignored", "Ignorado"),
        ],
        string="Estado Conciliación Falsa",
        default="pending",
        index=True,
        help="Estado de la sugerencia de conciliación falsa.",
    )
    fake_reconcile_score = fields.Float(
        string="Score",
        digits=(5, 2),
        help="Score del candidato sugerido (0-100).",
    )
    fake_reconcile_notes = fields.Text(
        string="Notas de Matching",
        help="Descripción de los criterios que generaron la sugerencia.",
    )
    candidate_payment_ids = fields.Many2many(
        comodel_name="account.payment",
        relation="account_bank_statement_line_candidate_payment_rel",
        column1="statement_line_id",
        column2="payment_id",
        string="Candidatos",
        compute="_compute_candidate_payment_ids",
        store=False,
        help="Top 5 candidatos de pago para esta línea de extracto.",
    )

    @api.depends("suggested_payment_id", "fake_reconcile_state")
    def _compute_candidate_payment_ids(self):
        """Calcula los candidatos disponibles para mostrar en la vista."""
        for st_line in self:
            candidates = st_line._sng_fake_reconcile_find_candidates(limit=5)
            st_line.candidate_payment_ids = [c["payment"].id for c in candidates]

    # -------------------------------------------------------------------------
    # Acciones públicas
    # -------------------------------------------------------------------------

    def action_sng_fake_reconcile_search(self):
        """Busca y aplica sugerencias de conciliación falsa para las líneas seleccionadas."""
        for st_line in self:
            st_line._sng_fake_reconcile_apply()
        return {"type": "ir.actions.act_window_close"}

    def action_sng_fake_reconcile_confirm(self):
        """El usuario confirma la sugerencia (solo informativo)."""
        for st_line in self:
            if st_line.fake_reconcile_state != "suggested":
                raise UserError(_("Solo se pueden confirmar líneas con estado 'Sugerido'."))
            st_line.fake_reconcile_state = "confirmed"

    def action_sng_fake_reconcile_ignore(self):
        """El usuario ignora la sugerencia."""
        self.write({
            "fake_reconcile_state": "ignored",
        })

    def action_sng_fake_reconcile_reset(self):
        """Vuelve la línea a estado pendiente y limpia la sugerencia."""
        self.write({
            "suggested_payment_id": False,
            "fake_reconcile_state": "pending",
            "fake_reconcile_score": 0.0,
            "fake_reconcile_notes": False,
        })

    # -------------------------------------------------------------------------
    # Lógica de matching/scoring
    # -------------------------------------------------------------------------

    def _sng_fake_reconcile_apply(self):
        """Ejecuta el matching y actualiza campos informativos sin tocar asientos."""
        self.ensure_one()
        if self.fake_reconcile_state in ("confirmed", "ignored"):
            return

        config = self.env["sng.fake.reconcile.config"].get_config_for_journal(self.journal_id)
        if not config:
            self.write({
                "suggested_payment_id": False,
                "fake_reconcile_state": "pending",
                "fake_reconcile_score": 0.0,
                "fake_reconcile_notes": _("No existe configuración de conciliación falsa para este diario."),
            })
            return

        candidates = self._sng_fake_reconcile_find_candidates(config=config)
        if not candidates:
            self.write({
                "suggested_payment_id": False,
                "fake_reconcile_state": "pending",
                "fake_reconcile_score": 0.0,
                "fake_reconcile_notes": _("No se encontraron pagos candidatos."),
            })
            return

        best = candidates[0]
        second = candidates[1] if len(candidates) > 1 else {"score": 0.0}

        if (
            best["score"] >= config.min_score_to_suggest
            and (best["score"] - second["score"]) >= config.min_score_gap
        ):
            self.write({
                "suggested_payment_id": best["payment"].id,
                "fake_reconcile_state": "suggested",
                "fake_reconcile_score": best["score"],
                "fake_reconcile_notes": best["notes"],
            })
        else:
            self.write({
                "suggested_payment_id": False,
                "fake_reconcile_state": "pending",
                "fake_reconcile_score": best["score"],
                "fake_reconcile_notes": _(
                    "Mejor candidato: %(payment)s (score %(score).1f). No superó el umbral de confianza.",
                    payment=best["payment"].display_name,
                    score=best["score"],
                ),
            })

    def _sng_fake_reconcile_find_candidates(self, config=None, limit=None):
        """Busca pagos candidatos y retorna lista ordenada por score descendente.

        :return: list[dict] con keys: payment, score, notes
        """
        self.ensure_one()
        if not config:
            config = self.env["sng.fake.reconcile.config"].get_config_for_journal(self.journal_id)
        if not config:
            return []

        candidates = self._sng_fake_reconcile_get_base_candidates(config)
        scored = []
        for payment in candidates:
            score, notes = self._sng_fake_reconcile_score_payment(payment, config)
            if score > 0:
                scored.append({
                    "payment": payment,
                    "score": score,
                    "notes": notes,
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        if limit:
            scored = scored[:limit]
        return scored

    def _sng_fake_reconcile_get_base_candidates(self, config):
        """Devuelve recordset de account.payment candidatos según filtros base."""
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("state", "in", ("in_process", "paid")),
            ("payment_type", "=", "inbound"),
            ("is_reconciled", "=", False),
            ("date", ">=", self.date - timedelta(days=config.date_tolerance_days)),
            ("date", "<=", self.date + timedelta(days=config.date_tolerance_days)),
        ]
        if self.journal_id:
            domain.append(("journal_id", "=", self.journal_id.id))

        candidates = self.env["account.payment"].search(domain)

        # Filtrar por tolerancia de monto
        amount_tolerance = abs(self.amount) * config.amount_tolerance_pct if config.amount_tolerance_pct else 0.0
        min_amount = abs(self.amount) - amount_tolerance
        max_amount = abs(self.amount) + amount_tolerance

        filtered = candidates.browse()
        for payment in candidates:
            payment_amount = self._sng_fake_reconcile_convert_payment_amount(payment)
            if payment_amount is None:
                continue
            if min_amount <= abs(payment_amount) <= max_amount:
                filtered |= payment

        return filtered

    def _sng_fake_reconcile_convert_payment_amount(self, payment):
        """Convierte el monto del pago a la moneda de la línea de extracto."""
        self.ensure_one()
        st_currency = self.currency_id
        if not st_currency:
            st_currency = self.company_id.currency_id

        payment_currency = payment.currency_id
        if not payment_currency:
            payment_currency = payment.company_id.currency_id

        if payment_currency == st_currency:
            return payment.amount

        # Conversión usando tipo de cambio de la fecha del pago
        return payment_currency._convert(
            payment.amount,
            st_currency,
            payment.company_id,
            payment.date,
        )

    def _sng_fake_reconcile_score_payment(self, payment, config):
        """Calcula score y notas para un pago candidato.

        :return: (score, notes)
        """
        self.ensure_one()
        score = 0.0
        notes_parts = []

        # 1. Monto
        if config.enable_amount_date_match:
            payment_amount = self._sng_fake_reconcile_convert_payment_amount(payment)
            if payment_amount is not None:
                st_amount = abs(self.amount)
                p_amount = abs(payment_amount)
                tolerance = st_amount * config.amount_tolerance_pct if config.amount_tolerance_pct else 0.0
                if st_amount == 0:
                    amount_score = 0.0
                elif p_amount == st_amount:
                    amount_score = 40.0
                elif tolerance:
                    diff = abs(p_amount - st_amount)
                    amount_score = 40.0 * max(0.0, 1.0 - (diff / tolerance))
                else:
                    amount_score = 0.0
                score += amount_score
                if amount_score >= 40.0:
                    notes_parts.append(_("monto exacto"))
                elif amount_score > 0:
                    notes_parts.append(_("monto aproximado"))

            # 2. Fecha
            date_diff = abs((payment.date - self.date).days)
            if date_diff <= config.date_tolerance_days:
                date_score = 20.0 * (1.0 - (date_diff / max(config.date_tolerance_days, 1)))
                score += date_score
                if date_score >= 20.0:
                    notes_parts.append(_("fecha exacta"))
                elif date_score > 0:
                    notes_parts.append(_("fecha cercana"))

        # 3. Partner
        if config.enable_partner_match:
            partner_score, partner_note = self._sng_fake_reconcile_score_partner(payment)
            score += partner_score
            if partner_note:
                notes_parts.append(partner_note)

        # 4. Referencia / factura
        if config.enable_reference_match:
            ref_score, ref_note = self._sng_fake_reconcile_score_reference(payment, config)
            score += ref_score
            if ref_note:
                notes_parts.append(ref_note)

        notes = "; ".join(notes_parts) if notes_parts else _("coincidencia débil")
        return min(score, 100.0), notes

    def _sng_fake_reconcile_score_partner(self, payment):
        """Puntúa coincidencia de partner."""
        self.ensure_one()
        if not payment.partner_id:
            return 0.0, ""

        if self.partner_id and self.partner_id == payment.partner_id:
            return 20.0, _("cliente coincide")

        if self.partner_name and self.partner_name.strip():
            partner_name = self.partner_name.strip().lower()
            payment_partner_name = payment.partner_id.name.strip().lower() if payment.partner_id.name else ""
            if partner_name == payment_partner_name:
                return 20.0, _("cliente coincide")

        if self.account_number and payment.partner_id.bank_ids:
            sanitized_payment_ref = payment.partner_id.bank_ids.mapped("acc_number")
            if self.account_number in sanitized_payment_ref:
                return 20.0, _("cuenta bancaria coincide")

        return 0.0, ""

    def _sng_fake_reconcile_score_reference(self, payment, config):
        """Puntúa coincidencia de referencia/factura."""
        self.ensure_one()
        if not config.reference_regex or not self.payment_ref:
            return 0.0, ""

        matches = re.findall(config.reference_regex, self.payment_ref or "", re.IGNORECASE)
        if not matches:
            return 0.0, ""

        references = set(str(m).lstrip("0") or "0" for m in (matches if isinstance(matches[0], tuple) else matches))

        # Buscar en nombre del pago
        payment_name = (payment.name or "").upper()
        for ref in references:
            if ref in payment_name:
                return 20.0, _("referencia coincide")

        # Buscar en facturas relacionadas
        invoice_names = set()
        if payment.reconciled_invoice_ids:
            invoice_names.update((payment.reconciled_invoice_ids.mapped("name") or []))
            invoice_names.update((payment.reconciled_invoice_ids.mapped("payment_reference") or []))
        if payment.move_id and payment.move_id.line_ids:
            reconciled_moves = payment.move_id.line_ids.matched_debit_ids.debit_move_id.move_id
            reconciled_moves |= payment.move_id.line_ids.matched_credit_ids.credit_move_id.move_id
            invoice_names.update(reconciled_moves.mapped("name"))
            invoice_names.update(reconciled_moves.mapped("payment_reference"))

        for inv_name in invoice_names:
            clean_name = (inv_name or "").upper()
            for ref in references:
                if ref in clean_name:
                    return 20.0, _("factura coincide")

        return 0.0, ""
