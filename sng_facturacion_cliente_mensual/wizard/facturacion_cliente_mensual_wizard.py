# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import date_utils

MONTH_NAMES = [
    "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO",
    "AGOSTO", "SETIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
]

# Columnas de cada bloque mensual, en el orden del Excel.
VALUE_KEYS = ("subtotal", "discount", "credit_note", "vnai", "tax", "total")


def _empty_values():
    return dict.fromkeys(VALUE_KEYS, 0.0)


class SngFacturacionClienteMensualWizard(models.TransientModel):
    _name = "sng.facturacion.cliente.mensual.wizard"
    _description = "Facturación por cliente mensual detallado"

    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )
    date_from = fields.Date(
        string="Mes desde",
        required=True,
        default=lambda self: date_utils.start_of(
            fields.Date.context_today(self), "month"
        ),
        help="Se toma desde el primer día de este mes.",
    )
    date_to = fields.Date(
        string="Mes hasta",
        required=True,
        default=lambda self: date_utils.end_of(
            fields.Date.context_today(self), "month"
        ),
        help="Se toma hasta el último día de este mes.",
    )
    partner_ids = fields.Many2many(
        "res.partner",
        "sng_fact_cli_mensual_partner_rel",
        "wizard_id",
        "partner_id",
        string="Clientes",
        domain=[("customer_rank", ">", 0)],
        help=(
            "Dejar vacío para incluir todos los clientes. Se incluyen las "
            "facturas del cliente comercial y de sus contactos o sucursales."
        ),
    )
    salesperson_ids = fields.Many2many(
        "res.partner",
        "sng_fact_cli_mensual_salesperson_rel",
        "wizard_id",
        "partner_id",
        string="Vendedores",
        domain=[("is_salesperson", "=", True)],
        help=(
            "Dejar vacío para incluir todos los vendedores. Filtra por el "
            "vendedor (contacto) de cada factura o nota de crédito."
        ),
    )

    # ------------------------------------------------------------------
    # Validaciones
    # ------------------------------------------------------------------
    @api.onchange("date_from")
    def _onchange_date_from(self):
        if self.date_from:
            self.date_from = date_utils.start_of(self.date_from, "month")

    @api.onchange("date_to")
    def _onchange_date_to(self):
        if self.date_to:
            self.date_to = date_utils.end_of(self.date_to, "month")

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wizard in self:
            if (
                wizard.date_from
                and wizard.date_to
                and wizard._get_period()[0] > wizard._get_period()[1]
            ):
                raise ValidationError(
                    _("El mes inicial no puede ser mayor que el mes final.")
                )

    def _check_company_access(self):
        self.ensure_one()
        if self.company_id not in self.env.companies:
            raise AccessError(
                _("No tiene acceso a la compañía seleccionada para el reporte.")
            )

    # ------------------------------------------------------------------
    # Período
    # ------------------------------------------------------------------
    def _get_period(self):
        """Rango normalizado a meses completos."""
        self.ensure_one()
        return (
            date_utils.start_of(self.date_from, "month"),
            date_utils.end_of(self.date_to, "month"),
        )

    def _get_months(self):
        """Lista de meses del rango: dicts con key, inicio, fin y etiqueta."""
        self.ensure_one()
        start, end = self._get_period()
        months = []
        current = start
        while current <= end:
            months.append(
                {
                    "key": (current.year, current.month),
                    "date_start": current,
                    "date_end": date_utils.end_of(current, "month"),
                    "label": "%s %s" % (MONTH_NAMES[current.month - 1], current.year),
                }
            )
            current = date_utils.add(current, months=1)
        return months

    # ------------------------------------------------------------------
    # Datos
    # ------------------------------------------------------------------
    def _get_moves_domain(self):
        self.ensure_one()
        start, end = self._get_period()
        domain = [
            ("state", "=", "posted"),
            ("move_type", "in", ("out_invoice", "out_refund")),
            ("company_id", "=", self.company_id.id),
            ("invoice_date", ">=", start),
            ("invoice_date", "<=", end),
        ]
        if self.partner_ids:
            domain.append(
                (
                    "commercial_partner_id",
                    "in",
                    self.partner_ids.commercial_partner_id.ids,
                )
            )
        if self.salesperson_ids:
            domain.append(("salesperson_id", "in", self.salesperson_ids.ids))
        return domain

    def _get_moves(self):
        self.ensure_one()
        self._check_company_access()
        return (
            self.env["account.move"]
            .with_company(self.company_id)
            .search(self._get_moves_domain(), order="invoice_date, id")
        )

    def _get_discounts_by_move(self, invoices):
        """Descuento por factura en moneda de la compañía.

        Se calcula en la moneda del documento (cantidad x precio x %desc)
        y se convierte con la misma tasa de la factura, así que
        subtotal neto + descuento = bruto exacto también en USD.
        """
        discounts = defaultdict(float)
        if not invoices:
            return discounts
        lines = self.env["account.move.line"].search(
            [
                ("move_id", "in", invoices.ids),
                ("display_type", "=", "product"),
                ("discount", "!=", 0),
            ]
        )
        company_currency = self.company_id.currency_id
        for line in lines:
            move = line.move_id
            rate = move.invoice_currency_rate or 1.0
            amount = line.quantity * line.price_unit * line.discount / 100.0
            discounts[move.id] += company_currency.round(abs(amount) / rate)
        return discounts

    @staticmethod
    def _partner_code(partner):
        code = partner.unique_id or ""
        return "" if code == "/" else code

    def _get_report_data(self):
        """Estructura del reporte.

        Devuelve ``months`` (lista de meses), ``rows`` (un dict por cliente
        comercial con ``code``, ``name``, ``months`` {key: valores} y
        ``period``) ordenadas por total del período descendente, y
        ``totals`` con los totales por mes y del período.
        """
        self.ensure_one()
        months = self._get_months()
        moves = self._get_moves()
        invoices = moves.filtered(lambda m: m.move_type == "out_invoice")
        discounts = self._get_discounts_by_move(invoices)

        by_partner = {}
        for move in moves:
            partner = move.commercial_partner_id
            entry = by_partner.get(partner.id)
            if entry is None:
                entry = by_partner[partner.id] = {
                    "partner": partner,
                    "code": self._partner_code(partner),
                    "name": partner.commercial_name or partner.name or "",
                    "months": defaultdict(_empty_values),
                }
            date = move.invoice_date
            values = entry["months"][(date.year, date.month)]
            if move.move_type == "out_invoice":
                discount = discounts.get(move.id, 0.0)
                values["subtotal"] += move.amount_untaxed_signed + discount
                values["discount"] += discount
                values["tax"] += move.amount_tax_signed
            else:
                # NC sin impuesto; su IVA (negativo) rebaja el impuesto del mes.
                values["credit_note"] += abs(move.amount_untaxed_signed)
                values["tax"] += move.amount_tax_signed

        totals = {"months": defaultdict(_empty_values), "period": _empty_values()}
        rows = []
        for entry in by_partner.values():
            period = _empty_values()
            for key, values in entry["months"].items():
                # VNAI: venta neta antes de impuesto.
                values["vnai"] = (
                    values["subtotal"] - values["discount"] - values["credit_note"]
                )
                values["total"] = values["vnai"] + values["tax"]
                for value_key in VALUE_KEYS:
                    period[value_key] += values[value_key]
                    totals["months"][key][value_key] += values[value_key]
            for value_key in VALUE_KEYS:
                totals["period"][value_key] += period[value_key]
            entry["period"] = period
            rows.append(entry)

        rows.sort(key=lambda r: (-r["period"]["total"], r["code"], r["name"]))
        return {"months": months, "rows": rows, "totals": totals}

    def _get_filters_description(self):
        self.ensure_one()
        parts = []
        if self.salesperson_ids:
            parts.append(
                _("Vendedores: %s")
                % ", ".join(self.salesperson_ids.mapped("display_name"))
            )
        if self.partner_ids:
            parts.append(
                _("Clientes: %s")
                % ", ".join(
                    p.commercial_name or p.name for p in self.partner_ids
                )
            )
        return " | ".join(parts)

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_export_xlsx(self):
        self.ensure_one()
        self._check_dates()
        if not self._get_moves():
            raise UserError(
                _(
                    "No se encontraron facturas ni notas de crédito publicadas "
                    "para el período y los filtros seleccionados."
                )
            )
        return self.env.ref(
            "sng_facturacion_cliente_mensual.action_facturacion_cliente_mensual_xlsx"
        ).report_action(self)
