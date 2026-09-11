# -*- coding: utf-8 -*-
"""Reglas de tipo de documento y numeración para facturas de proveedor.

Problema que corrige (ver cr_electronic_invoice):

* ``create()`` asigna FE/TE a cualquier factura con proveedor con cédula, aunque
  sea una factura de proveedor. Con FE/TE la factura no cae en el camino
  "disabled" y Odoo la numera con la numeración estándar del diario, que copia
  el patrón del último asiento publicado (un consecutivo FEC o un número DA).
* En el camino "disabled" cr_electronic_invoice sobreescribe el nombre con la
  secuencia ``sequence.DA``; así conviven dos contadores sobre el mismo patrón
  y aparece "Ya existe otro asiento con el mismo nombre".
* Cualquier factura de proveedor costarricense sin XML se convierte en FEC y
  consume la secuencia FEC del diario, aunque no se quisiera emitir una FEC.

Reglas nuevas para ``in_invoice`` / ``in_refund``:

* Es **FEC** solo si el diario tiene secuencia FEC, es ``in_invoice`` y no
  trae XML del proveedor. En cualquier otro caso es ``disabled``.
* Un diario con secuencia FEC es exclusivo para FEC: no se puede publicar ahí
  una factura de proveedor con XML.
* Las facturas ``disabled`` conservan el nombre estándar del diario; nunca
  consumen ``sequence.DA``.
* Los mensajes receptor (CCE/CPCE/RCE) los sigue asignando
  cr_electronic_invoice después de publicar y no se tocan.
* La numeración estándar de una factura de proveedor solo toma como referencia
  nombres con el formato del diario (``FACTU/AAAA/MM/0001``, ``RFACTU/...``).
  Odoo copia el patrón del último asiento nombrado del diario; con el histórico
  de nombres DA########## y consecutivos FEC de 20 dígitos, sin este filtro
  seguiría generando esos patrones para siempre.
"""
from odoo import _, api, models
from odoo.exceptions import UserError

VENDOR_TYPES = ("in_invoice", "in_refund")
# Tipos que este módulo puede reasignar en borrador. Los mensajes receptor
# (CCE/CPCE/RCE) y REP quedan fuera.
MANAGED_TIPOS = (False, "FE", "FEE", "TE", "NC", "ND", "FEC", "disabled")


class AccountMove(models.Model):
    _inherit = "account.move"

    # ------------------------------------------------------------------
    # Cálculo del tipo de documento
    # ------------------------------------------------------------------
    def _sng_vendor_tipo_documento(self):
        self.ensure_one()
        if (
            self.move_type == "in_invoice"
            and self.journal_id.FEC_sequence_id
            and not self.xml_supplier_approval
        ):
            return "FEC"
        return "disabled"

    def _sng_sync_vendor_tipo_documento(self):
        """Alinea tipo_documento con el diario y el XML en borradores de proveedor."""
        for move in self:
            if (
                move.move_type not in VENDOR_TYPES
                or move.state != "draft"
                or move.tipo_documento not in MANAGED_TIPOS
            ):
                continue
            new_tipo = move._sng_vendor_tipo_documento()
            if move.tipo_documento != new_tipo:
                move.with_context(sng_fe_prov_sync=True).tipo_documento = new_tipo

    def _sng_check_fec_requirements(self):
        self.ensure_one()
        partner = self.partner_id
        missing = []
        if not partner:
            missing.append(_("proveedor"))
        else:
            if not partner.country_id or partner.country_id.code != "CR":
                missing.append(_("país Costa Rica en el proveedor"))
            if not partner.vat:
                missing.append(_("cédula del proveedor"))
            if not partner.identification_id:
                missing.append(_("tipo de identificación del proveedor"))
        if not self.economic_activity_id:
            missing.append(_("actividad económica"))
        if missing:
            raise UserError(
                _(
                    "No se puede emitir la Factura Electrónica de Compra (FEC) "
                    "en el diario %(journal)s. Falta: %(missing)s.\n\n"
                    "Complete los datos o registre la factura en un diario de "
                    "compras sin secuencia FEC."
                )
                % {
                    "journal": self.journal_id.display_name,
                    "missing": ", ".join(missing),
                }
            )

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        Journal = self.env["account.journal"]
        for vals in vals_list:
            move_type = vals.get("move_type") or self._context.get("default_move_type")
            if move_type not in VENDOR_TYPES or vals.get("tipo_documento"):
                continue
            journal_id = vals.get("journal_id") or self._context.get("default_journal_id")
            journal = Journal.browse(journal_id) if journal_id else Journal
            if (
                move_type == "in_invoice"
                and journal
                and journal.FEC_sequence_id
                and not vals.get("xml_supplier_approval")
            ):
                vals["tipo_documento"] = "FEC"
            else:
                vals["tipo_documento"] = "disabled"
        moves = super().create(vals_list)
        # El diario puede haberse calculado en create o venir con FE por defecto.
        moves._sng_sync_vendor_tipo_documento()
        return moves

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("sng_fe_prov_sync") and any(
            key in vals for key in ("journal_id", "xml_supplier_approval", "move_type")
        ):
            self._sng_sync_vendor_tipo_documento()
        return res

    @api.onchange("journal_id", "xml_supplier_approval")
    def _onchange_sng_vendor_tipo_documento(self):
        for move in self:
            if (
                move.move_type in VENDOR_TYPES
                and move.state == "draft"
                and move.tipo_documento in MANAGED_TIPOS
            ):
                move.tipo_documento = move._sng_vendor_tipo_documento()

    # ------------------------------------------------------------------
    # Hooks de cr_electronic_invoice
    # ------------------------------------------------------------------
    def _electronic_documents_disabled(self):
        self.ensure_one()
        if self.move_type in VENDOR_TYPES and self.tipo_documento != "FEC":
            return True
        return super()._electronic_documents_disabled()

    def _next_disabled_document_sequence(self):
        """Facturas de proveedor: no consumir sequence.DA; devolver False hace
        que cr_electronic_invoice conserve el nombre estándar del diario."""
        self.ensure_one()
        if self.move_type in VENDOR_TYPES:
            return False
        return super()._next_disabled_document_sequence()

    # ------------------------------------------------------------------
    # Numeración estándar: ignorar nombres heredados (DA, consecutivos FEC)
    # ------------------------------------------------------------------
    def _sng_standard_name_prefix(self):
        """Prefijo con el que Odoo iniciaría la numeración de este asiento
        (mismo criterio que ``_get_starting_sequence``)."""
        self.ensure_one()
        prefix = "%s/" % self.journal_id.code
        if self.journal_id.refund_sequence and self.move_type in ("out_refund", "in_refund"):
            prefix = "R" + prefix
        return prefix

    def _sng_use_standard_vendor_numbering(self):
        self.ensure_one()
        return (
            self.move_type in VENDOR_TYPES
            and self.journal_id.type == "purchase"
            and not self.journal_id.payment_sequence
        )

    def _get_last_sequence_domain(self, relaxed=False):
        # EXTENDS account: misma lógica que account.move, pero restringida a
        # nombres que empiezan con el prefijo estándar del diario.
        self.ensure_one()
        if not self._sng_use_standard_vendor_numbering():
            return super()._get_last_sequence_domain(relaxed)
        if not self.date or not self.journal_id:
            return "WHERE FALSE", {}

        prefix = self._sng_standard_name_prefix()
        where_string = (
            "WHERE journal_id = %(journal_id)s AND name != '/' "
            "AND name LIKE %(sng_prefix_like)s"
        )
        param = {
            "journal_id": self.journal_id.id,
            "sng_prefix_like": prefix.replace("_", "\\_") + "%",
        }

        if not relaxed:
            domain = [
                ("journal_id", "=", self.journal_id.id),
                ("id", "!=", self.id or self._origin.id),
                ("name", "=like", prefix + "%"),
            ]
            if self.journal_id.refund_sequence:
                refund_types = ("out_refund", "in_refund")
                domain += [
                    (
                        "move_type",
                        "in" if self.move_type in refund_types else "not in",
                        refund_types,
                    )
                ]
            reference_move_name = (
                self.sudo()
                .search(domain + [("date", "<=", self.date)], order="date desc", limit=1)
                .name
            )
            if not reference_move_name:
                reference_move_name = self.sudo().search(domain, order="date asc", limit=1).name
            sequence_number_reset = self._deduce_sequence_number_reset(reference_move_name)
            date_start, date_end, *_ = self._get_sequence_date_range(sequence_number_reset)
            where_string += " AND date BETWEEN %(date_start)s AND %(date_end)s"
            param["date_start"] = date_start
            param["date_end"] = date_end

            if sequence_number_reset in ("year", "year_range"):
                param["anti_regex"] = (
                    self._make_regex_non_capturing(
                        self._sequence_monthly_regex.split("(?P<seq>")[0]
                    )
                    + "$"
                )
            elif sequence_number_reset == "never":
                param["anti_regex"] = (
                    self._make_regex_non_capturing(
                        self._sequence_yearly_regex.split("(?P<seq>")[0]
                    )
                    + "$"
                )
            if param.get("anti_regex") and not self.journal_id.sequence_override_regex:
                where_string += " AND sequence_prefix !~ %(anti_regex)s "

        if self.journal_id.refund_sequence:
            if self.move_type in ("out_refund", "in_refund"):
                where_string += " AND move_type IN ('out_refund', 'in_refund') "
            else:
                where_string += " AND move_type NOT IN ('out_refund', 'in_refund') "

        return where_string, param

    def action_post(self):
        vendor = self.filtered(
            lambda m: m.move_type in VENDOR_TYPES and m.state == "draft"
        )
        vendor._sng_sync_vendor_tipo_documento()
        for move in vendor:
            if (
                move.move_type == "in_invoice"
                and move.journal_id.FEC_sequence_id
                and move.tipo_documento != "FEC"
            ):
                raise UserError(
                    _(
                        "El diario %s es exclusivo para Facturas Electrónicas de "
                        "Compra (FEC). Esta factura trae XML del proveedor; "
                        "regístrela en un diario de compras sin secuencia FEC."
                    )
                    % move.journal_id.display_name
                )
            if move.tipo_documento == "FEC":
                move._sng_check_fec_requirements()

        # cr_electronic_invoice publica con super() sobre todo el recordset dentro
        # de un bucle por factura; al publicar varias facturas de proveedor a la
        # vez la segunda iteración vuelve a publicar asientos ya publicados.
        # Se publican una por una para evitarlo.
        if len(vendor) > 1:
            res = None
            for move in self:
                res = super(AccountMove, move).action_post()
            return res
        return super().action_post()
