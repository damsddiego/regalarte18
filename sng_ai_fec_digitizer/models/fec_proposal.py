# -*- coding: utf-8 -*-
import base64
import io
import json
import re
from collections import Counter

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare


def _number(value, default=0.0):
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


class SngAiFecProposal(models.Model):
    _name = "sng.ai.fec.proposal"
    _description = "Propuesta de Factura Electrónica de Compra"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "batch_id desc, first_page, id"

    name = fields.Char(compute="_compute_name", store=True)
    batch_id = fields.Many2one("sng.ai.fec.batch", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="batch_id.company_id", store=True, index=True)
    state = fields.Selection(
        [("review", "Por revisar"), ("ready", "Lista"), ("invoice", "Factura creada"),
         ("duplicate", "Duplicada"), ("discarded", "Descartada")],
        default="review", required=True, tracking=True, index=True,
    )
    page_numbers = fields.Char(string="Páginas", required=True, tracking=True)
    first_page = fields.Integer(compute="_compute_first_page", store=True)
    preview_image = fields.Image(string="Vista previa", compute="_compute_preview_image", attachment=True)
    supplier_name = fields.Char(string="Proveedor detectado", tracking=True)
    supplier_vat = fields.Char(string="Identificación detectada", tracking=True)
    supplier_activity = fields.Char(string="Actividad detectada")
    partner_id = fields.Many2one("res.partner", string="Proveedor Odoo", tracking=True, index=True)
    invoice_date = fields.Date(string="Fecha", tracking=True)
    reference = fields.Char(string="Número de comprobante", tracking=True)
    currency_id = fields.Many2one("res.currency", required=True, default=lambda self: self.env.ref("base.CRC", raise_if_not_found=False) or self.env.company.currency_id)
    payment_method_id = fields.Many2one("payment.methods", string="Medio de pago")
    payment_condition = fields.Char(string="Condición detectada")
    simplified_regime = fields.Boolean(string="Régimen simplificado")
    economic_activity_id = fields.Many2one("economic.activity", string="Actividad del proveedor")
    journal_id = fields.Many2one("account.journal", string="Diario", domain="[('type','=','purchase'), ('company_id','=',company_id)]")
    line_ids = fields.One2many("sng.ai.fec.proposal.line", "proposal_id", string="Líneas", copy=True)
    subtotal = fields.Monetary(currency_field="currency_id")
    tax_total = fields.Monetary(currency_field="currency_id")
    total = fields.Monetary(currency_field="currency_id", tracking=True)
    confidence = fields.Float(string="Confianza global", digits=(4, 3))
    confidence_json = fields.Text(groups="sng_ai_fec_digitizer.group_fec_digitizer_manager")
    warning_message = fields.Html(string="Advertencias", sanitize=True, readonly=True)
    duplicate_proposal_id = fields.Many2one("sng.ai.fec.proposal", readonly=True)
    duplicate_move_id = fields.Many2one("account.move", readonly=True)
    invoice_id = fields.Many2one("account.move", readonly=True, copy=False, index=True)
    historical_match_rate = fields.Float(string="Coincidencia histórica", readonly=True)
    history_invoice_count = fields.Integer(string="Antecedentes", readonly=True)
    history_applied = fields.Boolean(string="Patrón aplicado", readonly=True)

    @api.depends("supplier_name", "reference", "batch_id")
    def _compute_name(self):
        for proposal in self:
            proposal.name = "%s - %s" % (proposal.supplier_name or _("Proveedor sin identificar"), proposal.reference or _("Sin número"))

    @api.depends("page_numbers")
    def _compute_first_page(self):
        for proposal in self:
            pages = proposal._get_pages(silent=True)
            proposal.first_page = min(pages) if pages else 0

    @api.depends("page_numbers", "batch_id.pdf_data")
    def _compute_preview_image(self):
        for proposal in self:
            proposal.preview_image = False
            pages = proposal._get_pages(silent=True)
            if not pages or not proposal.batch_id.pdf_data:
                continue
            try:
                images = proposal.batch_id._render_pages(base64.b64decode(proposal.batch_id.pdf_data), proposal.batch_id.page_count or 100)
                proposal.preview_image = base64.b64encode(images[pages[0] - 1])
            except Exception:
                proposal.preview_image = False

    @api.constrains("page_numbers")
    def _check_page_numbers(self):
        for proposal in self:
            proposal._get_pages()

    def _get_pages(self, silent=False):
        self.ensure_one()
        try:
            pages = sorted(set(int(value.strip()) for value in (self.page_numbers or "").split(",") if value.strip()))
            maximum = self.batch_id.page_count
            if not pages or any(page < 1 or (maximum and page > maximum) for page in pages):
                raise ValueError
            return pages
        except ValueError:
            if silent:
                return []
            raise ValidationError(_("Use páginas separadas por coma dentro del rango del PDF."))

    @api.model
    def _values_from_ai(self, data, page_count):
        if not isinstance(data, dict):
            raise UserError(_("Un documento extraído tiene formato inválido."))
        pages = data.get("pages") or []
        try:
            pages = sorted(set(int(page) for page in pages))
        except (TypeError, ValueError):
            pages = []
        if not pages or any(page < 1 or page > page_count for page in pages):
            raise UserError(_("La IA devolvió una agrupación de páginas inválida."))
        confidence = data.get("confidence") if isinstance(data.get("confidence"), dict) else {}
        confidence_values = [_number(value) for value in confidence.values() if isinstance(value, (int, float))]
        currency = self.env["res.currency"].search([("name", "=", data.get("currency") or "CRC")], limit=1)
        payment = self.env["payment.methods"].search([("sequence", "=", str(data.get("payment_method_code") or "").zfill(2))], limit=1)
        date_value = data.get("invoice_date")
        try:
            invoice_date = fields.Date.to_date(date_value) if date_value else False
        except (TypeError, ValueError):
            invoice_date = False
        lines = data.get("lines") if isinstance(data.get("lines"), list) else []
        return {
            # Explicitly override any default_state inherited from the parent action.
            "state": "review",
            "page_numbers": ",".join(map(str, pages)),
            "supplier_name": data.get("supplier_name"), "supplier_vat": data.get("supplier_vat"),
            "supplier_activity": data.get("supplier_activity"), "reference": data.get("reference"),
            "invoice_date": invoice_date, "currency_id": currency.id or self.env.company.currency_id.id,
            "payment_method_id": payment.id, "payment_condition": data.get("payment_condition"),
            "simplified_regime": bool(data.get("simplified_regime")),
            "subtotal": _number(data.get("subtotal")), "tax_total": _number(data.get("tax_total")),
            "total": _number(data.get("total")),
            "confidence": sum(confidence_values) / len(confidence_values) if confidence_values else 0.0,
            "confidence_json": json.dumps(confidence, ensure_ascii=False),
            "line_ids": [Command.create({
                "description": line.get("description") or _("Concepto no identificado"),
                "quantity": _number(line.get("quantity"), 1.0) or 1.0,
                "unit_price": _number(line.get("unit_price")), "discount": _number(line.get("discount")),
                "detected_tax_rate": _number(line.get("tax_rate")), "detected_total": _number(line.get("total")),
            }) for line in lines if isinstance(line, dict)],
        }

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        for proposal in self:
            if proposal.partner_id:
                proposal.economic_activity_id = proposal.partner_id.activity_id
                proposal.payment_method_id = proposal.partner_id.payment_methods_id or proposal.payment_method_id
                proposal._apply_history()

    def _find_partner_by_vat(self):
        self.ensure_one()
        vat = re.sub(r"\D", "", self.supplier_vat or "")
        if not vat:
            return self.env["res.partner"]
        self.env.cr.execute(
            "SELECT id FROM res_partner WHERE active AND regexp_replace(COALESCE(vat,''), '[^0-9]', '', 'g') = %s ORDER BY company_id NULLS FIRST, id LIMIT 2",
            [vat],
        )
        ids = [row[0] for row in self.env.cr.fetchall()]
        return self.env["res.partner"].browse(ids[:1]) if len(ids) == 1 else self.env["res.partner"]

    def _match_partner_and_history(self):
        for proposal in self:
            if not proposal.partner_id:
                proposal.partner_id = proposal._find_partner_by_vat()
            if proposal.partner_id:
                activity_code = (proposal.supplier_activity or "").replace(".", "")
                proposal.economic_activity_id = proposal.partner_id.activity_id or self.env["economic.activity"].search([
                    ("company_id", "=", proposal.company_id.id), ("code", "in", [proposal.supplier_activity, activity_code])
                ], limit=1)
                proposal.payment_method_id = proposal.payment_method_id or proposal.partner_id.payment_methods_id
                proposal._apply_history()
            proposal.journal_id = proposal.journal_id or proposal._default_journal()

    def _default_journal(self):
        self.ensure_one()
        journal_param = self.env["ir.config_parameter"].sudo().get_param("sng_ai_fec_digitizer.journal_id")
        journal = self.env["account.journal"].browse(int(journal_param)) if journal_param and journal_param.isdigit() else self.env["account.journal"]
        if not journal.exists() or journal.company_id != self.company_id or journal.type != "purchase":
            journal = self.env["account.journal"].search([("type", "=", "purchase"), ("company_id", "=", self.company_id.id)], limit=1)
        return journal

    def _history_signature(self, move):
        lines = move.invoice_line_ids.filtered(lambda line: line.display_type == "product")
        if len(lines) != 1:
            return False
        line = lines[0]
        return (line.product_id.id, line.account_id.id, tuple(sorted(line.tax_ids.ids)), line.product_uom_id.id,
                move.payment_methods_id.id, move.partner_economic_activity_id.id or move.economic_activity_id.id)

    def _apply_history(self):
        for proposal in self.filtered("partner_id"):
            history = self.env["account.move"].search([
                ("company_id", "=", proposal.company_id.id), ("partner_id", "=", proposal.partner_id.id),
                ("move_type", "=", "in_invoice"), ("tipo_documento", "=", "FEC"), ("state", "=", "posted"),
            ], order="invoice_date desc, id desc", limit=20)
            signatures = [proposal._history_signature(move) for move in history]
            signatures = [signature for signature in signatures if signature]
            proposal.history_invoice_count = len(history)
            if not signatures:
                return
            signature, count = Counter(signatures).most_common(1)[0]
            rate = count / len(history) if history else 0.0
            proposal.historical_match_rate = rate
            if len(history) < 3 or rate < 0.80 or len(proposal.line_ids) != 1:
                return
            product_id, account_id, tax_ids, uom_id, payment_id, activity_id = signature
            line = proposal.line_ids[0]
            line.write({"product_id": product_id, "account_id": account_id,
                        "tax_ids": [Command.set(tax_ids)], "uom_id": uom_id, "source": "history"})
            if proposal.partner_id.import_bill_expense_account_id:
                line.account_id = proposal.partner_id.import_bill_expense_account_id
            proposal.payment_method_id = proposal.payment_method_id or payment_id
            proposal.economic_activity_id = proposal.economic_activity_id or activity_id
            proposal.history_applied = True

    def _duplicate_matches(self):
        self.ensure_one()
        if not self.partner_id or not self.reference:
            return self.env["sng.ai.fec.proposal"], self.env["account.move"]
        proposals = self.search([
            ("id", "!=", self.id), ("company_id", "=", self.company_id.id),
            ("partner_id", "=", self.partner_id.id), ("reference", "=", self.reference),
            ("state", "not in", ("discarded",)),
        ], limit=1)
        moves = self.env["account.move"].search([
            ("company_id", "=", self.company_id.id), ("partner_id", "=", self.partner_id.id),
            ("move_type", "=", "in_invoice"), ("ref", "=", self.reference), ("state", "!=", "cancel"),
        ], limit=1)
        if moves and self.invoice_id == moves:
            moves = self.env["account.move"]
        return proposals, moves

    def _refresh_warnings(self):
        threshold = float(self.env["ir.config_parameter"].sudo().get_param("sng_ai_fec_digitizer.confidence_threshold", 0.80))
        for proposal in self:
            warnings = []
            duplicate_proposal, duplicate_move = proposal._duplicate_matches()
            proposal.duplicate_proposal_id = duplicate_proposal
            proposal.duplicate_move_id = duplicate_move
            if proposal.confidence < threshold:
                warnings.append(_("Confianza %.0f%% inferior al umbral %.0f%%.") % (proposal.confidence * 100, threshold * 100))
            if not proposal.partner_id:
                warnings.append(_("No se encontró un proveedor único por identificación."))
            if duplicate_proposal or duplicate_move:
                warnings.append(_("Existe un posible comprobante duplicado."))
            if proposal.total and proposal.line_ids:
                calculated = sum(line.detected_total or line.quantity * line.unit_price * (1 - line.discount / 100) for line in proposal.line_ids)
                calculated += proposal.tax_total
                if float_compare(calculated, proposal.total, precision_rounding=proposal.currency_id.rounding) != 0:
                    warnings.append(_("La suma detectada de líneas e impuestos no coincide con el total."))
            proposal.warning_message = "<ul>%s</ul>" % "".join("<li>%s</li>" % warning for warning in warnings) if warnings else False

    def action_validate_ready(self):
        for proposal in self:
            proposal._refresh_warnings()
            proposal._validate_for_invoice()
            proposal.state = "ready"

    def _validate_for_invoice(self):
        self.ensure_one()
        missing = []
        for value, label in [
            (self.partner_id, _("Proveedor")), (self.reference, _("Número de comprobante")),
            (self.invoice_date, _("Fecha")), (self.journal_id, _("Diario")),
            (self.payment_method_id, _("Medio de pago")), (self.economic_activity_id, _("Actividad económica")),
            (self.line_ids, _("Líneas")),
        ]:
            if not value:
                missing.append(label)
        partner = self.partner_id
        if partner and (not partner.country_id or partner.country_id.code != "CR" or not partner.vat or not partner.identification_id):
            missing.append(_("Proveedor costarricense con identificación completa"))
        if self.journal_id and not self.journal_id.FEC_sequence_id:
            missing.append(_("Secuencia FEC en el diario"))
        for line in self.line_ids:
            if not line.product_id or not line.account_id or not line.uom_id:
                missing.append(_("Producto, cuenta y unidad en todas las líneas"))
                break
            cabys = line.product_id.cabys_code or line.product_id.categ_id.cabys_code
            if not cabys or len(cabys) != 13:
                missing.append(_("CABYS válido de 13 dígitos en todas las líneas"))
                break
        duplicate_proposal, duplicate_move = self._duplicate_matches()
        if duplicate_proposal or duplicate_move:
            missing.append(_("Resolver el posible duplicado"))
        if missing:
            raise UserError(_("La propuesta no está lista:\n- %s") % "\n- ".join(dict.fromkeys(missing)))

    def action_create_invoice(self):
        self.ensure_one()
        if self.invoice_id:
            return self.action_open_invoice()
        self._validate_for_invoice()
        line_commands = [Command.create({
            "product_id": line.product_id.id, "name": line.description,
            "quantity": line.quantity, "price_unit": line.unit_price, "discount": line.discount,
            "product_uom_id": line.uom_id.id, "account_id": line.account_id.id,
            "tax_ids": [Command.set(line.tax_ids.ids)],
        }) for line in self.line_ids]
        move = self.env["account.move"].with_company(self.company_id).create({
            "move_type": "in_invoice", "tipo_documento": "FEC", "xml_supplier_approval": False,
            "company_id": self.company_id.id, "journal_id": self.journal_id.id,
            "partner_id": self.partner_id.id, "ref": self.reference, "invoice_date": self.invoice_date,
            "currency_id": self.currency_id.id, "payment_methods_id": self.payment_method_id.id,
            "economic_activity_id": self.economic_activity_id.id,
            "partner_economic_activity_id": self.economic_activity_id.id,
            "invoice_line_ids": line_commands, "sng_ai_fec_proposal_id": self.id,
        })
        attachment = self._create_document_attachment(move)
        self.write({"invoice_id": move.id, "state": "invoice"})
        self.message_post(body=_("Factura borrador creada: %s") % move.display_name, attachment_ids=attachment.ids)
        if all(item.state in ("invoice", "discarded", "duplicate") for item in self.batch_id.proposal_ids):
            self.batch_id.state = "done"
        return self.action_open_invoice()

    def _create_document_attachment(self, move):
        try:
            from PyPDF2 import PdfReader, PdfWriter
        except ImportError as error:
            raise UserError(_("Falta la dependencia Python PyPDF2.")) from error
        reader = PdfReader(io.BytesIO(base64.b64decode(self.batch_id.pdf_data)))
        writer = PdfWriter()
        for page in self._get_pages():
            writer.add_page(reader.pages[page - 1])
        output = io.BytesIO()
        writer.write(output)
        return self.env["ir.attachment"].create({
            "name": "FEC_%s.pdf" % re.sub(r"[^A-Za-z0-9_.-]", "_", self.reference or str(self.id)),
            "type": "binary", "datas": base64.b64encode(output.getvalue()), "mimetype": "application/pdf",
            "res_model": "account.move", "res_id": move.id,
        })

    def action_open_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_("Todavía no existe una factura."))
        return {"type": "ir.actions.act_window", "res_model": "account.move", "res_id": self.invoice_id.id,
                "view_mode": "form", "target": "current"}

    def action_discard(self):
        self.filtered(lambda proposal: not proposal.invoice_id).write({"state": "discarded"})


class SngAiFecProposalLine(models.Model):
    _name = "sng.ai.fec.proposal.line"
    _description = "Línea de propuesta FEC IA"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    proposal_id = fields.Many2one("sng.ai.fec.proposal", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="proposal_id.company_id", store=True)
    currency_id = fields.Many2one(related="proposal_id.currency_id")
    description = fields.Char(required=True)
    quantity = fields.Float(default=1.0, required=True)
    unit_price = fields.Monetary(currency_field="currency_id", required=True)
    discount = fields.Float()
    detected_tax_rate = fields.Float(string="IVA detectado (%)")
    detected_total = fields.Monetary(currency_field="currency_id")
    product_id = fields.Many2one("product.product", domain="[('purchase_ok','=',True)]")
    account_id = fields.Many2one("account.account", domain="[('deprecated','=',False), ('account_type','in',('expense','expense_direct_cost','expense_depreciation'))]")
    tax_ids = fields.Many2many("account.tax", string="Impuestos", domain="[('type_tax_use','=','purchase'), ('company_id','=',company_id)]")
    uom_id = fields.Many2one("uom.uom", string="Unidad")
    cabys_code = fields.Char(compute="_compute_cabys")
    source = fields.Selection([("manual", "Manual"), ("history", "Historial"), ("ai", "IA")], default="ai", readonly=True)

    @api.depends("product_id", "product_id.cabys_code", "product_id.categ_id.cabys_code")
    def _compute_cabys(self):
        for line in self:
            line.cabys_code = line.product_id.cabys_code or line.product_id.categ_id.cabys_code

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for line in self:
            if not line.product_id:
                continue
            line.uom_id = line.product_id.uom_po_id or line.product_id.uom_id
            line.account_id = line.proposal_id.partner_id.import_bill_expense_account_id or line.product_id.property_account_expense_id or line.product_id.categ_id.property_account_expense_categ_id
            line.tax_ids = line.product_id.supplier_taxes_id.filtered(lambda tax: tax.company_id == line.company_id)
            line.source = "manual"

    def write(self, vals):
        tracked = {"description", "quantity", "unit_price", "discount", "product_id", "account_id", "tax_ids", "uom_id"} & set(vals)
        result = super().write(vals)
        if tracked and not self.env.context.get("skip_fec_audit"):
            for proposal in self.mapped("proposal_id"):
                proposal.message_post(body=_("Líneas revisadas manualmente. Campos modificados: %s") % ", ".join(sorted(tracked)))
        return result
