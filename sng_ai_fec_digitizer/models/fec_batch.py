# -*- coding: utf-8 -*-
import base64
import io
import json
import logging
import re

import requests

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

PRICING = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "deepseek-v4-flash": (0.14, 0.28),
    "deepseek-v4-pro": (0.435, 0.87),
}

EXTRACTION_PROMPT = """Analiza estas páginas de comprobantes costarricenses candidatos a Factura
Electrónica de Compra. Agrupa páginas que pertenezcan al mismo comprobante. Devuelve solamente JSON
válido con {"documents": [...]}. Cada documento debe contener: pages (lista 1-based), supplier_name,
supplier_vat, supplier_activity, reference, invoice_date ISO YYYY-MM-DD o null, currency (CRC/USD),
payment_method_code (01 efectivo, 02 tarjeta u otro código conocido), payment_condition, subtotal,
tax_total, total, simplified_regime booleano, lines y confidence. Cada línea contiene description,
quantity, unit_price, discount, tax_rate y total. confidence contiene valores 0..1 para supplier_vat,
reference, invoice_date, total y lines. No inventes datos ilegibles: usa null y confianza baja.
Los números son valores decimales sin símbolos ni separadores de miles."""

NORMALIZATION_PROMPT = """Normaliza y valida la extracción JSON de comprobantes FEC. Conserva pages y
los datos legibles, corrige solamente formatos evidentes, verifica que líneas/subtotal/impuestos/total
sean coherentes y devuelve exclusivamente JSON con la misma raíz {"documents": [...]}.
No inventes identificaciones, fechas, impuestos ni montos. Si hay duda conserva null o confianza baja.
Extracción:\n%s"""


class SngAiFecBatch(models.Model):
    _name = "sng.ai.fec.batch"
    _description = "Lote de digitalización IA FEC"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(default=lambda self: _("Nuevo lote FEC"), required=True, tracking=True)
    pdf_data = fields.Binary(string="PDF", required=True, attachment=True)
    pdf_filename = fields.Char(string="Nombre del archivo", required=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    provider = fields.Selection(
        [("anthropic", "Anthropic"), ("deepseek", "Anthropic + DeepSeek")],
        required=True,
        default=lambda self: self.env["ir.config_parameter"].sudo().get_param(
            "sng_ai_dashboard.provider", "anthropic"
        ),
        tracking=True,
    )
    state = fields.Selection(
        [
            ("uploaded", "Cargado"),
            ("queued", "En cola"),
            ("processing", "Procesando"),
            ("review", "Por revisar"),
            ("done", "Finalizado"),
            ("error", "Error"),
            ("discarded", "Descartado"),
        ],
        default="uploaded",
        required=True,
        tracking=True,
        index=True,
    )
    page_count = fields.Integer(readonly=True)
    proposal_ids = fields.One2many("sng.ai.fec.proposal", "batch_id", string="Propuestas")
    proposal_count = fields.Integer(compute="_compute_counts")
    invoice_count = fields.Integer(compute="_compute_counts")
    anthropic_model = fields.Char(readonly=True, groups="sng_ai_fec_digitizer.group_fec_digitizer_manager")
    deepseek_model = fields.Char(readonly=True, groups="sng_ai_fec_digitizer.group_fec_digitizer_manager")
    anthropic_input_tokens = fields.Integer(readonly=True, groups="sng_ai_fec_digitizer.group_fec_digitizer_manager")
    anthropic_output_tokens = fields.Integer(readonly=True, groups="sng_ai_fec_digitizer.group_fec_digitizer_manager")
    deepseek_input_tokens = fields.Integer(readonly=True, groups="sng_ai_fec_digitizer.group_fec_digitizer_manager")
    deepseek_output_tokens = fields.Integer(readonly=True, groups="sng_ai_fec_digitizer.group_fec_digitizer_manager")
    cost_usd = fields.Float(readonly=True, digits=(12, 4), groups="sng_ai_fec_digitizer.group_fec_digitizer_manager")
    estimated_cost_usd = fields.Float(string="Costo estimado (USD)", readonly=True, digits=(12, 4))
    privacy_accepted = fields.Boolean(
        string="Autorizo el envío a proveedores de IA",
        tracking=True,
        help="Confirma que el PDF puede enviarse a Anthropic y, en el flujo DeepSeek, también a DeepSeek.",
    )
    privacy_accepted_by = fields.Many2one("res.users", readonly=True)
    privacy_accepted_at = fields.Datetime(readonly=True)
    raw_response = fields.Text(readonly=True, groups="sng_ai_fec_digitizer.group_fec_digitizer_manager")
    error_message = fields.Text(readonly=True)
    attempt_count = fields.Integer(readonly=True)
    processed_at = fields.Datetime(readonly=True)

    @api.depends("proposal_ids.state", "proposal_ids.invoice_id")
    def _compute_counts(self):
        for batch in self:
            batch.proposal_count = len(batch.proposal_ids)
            batch.invoice_count = len(batch.proposal_ids.filtered("invoice_id"))

    @api.constrains("pdf_filename", "pdf_data")
    def _check_pdf(self):
        for batch in self:
            if batch.pdf_filename and not batch.pdf_filename.lower().endswith(".pdf"):
                raise ValidationError(_("El archivo debe ser un PDF."))
            max_mb = int(self.env["ir.config_parameter"].sudo().get_param(
                "sng_ai_fec_digitizer.max_file_mb", 20
            ))
            if batch.pdf_data and len(base64.b64decode(batch.pdf_data)) > max_mb * 1024 * 1024:
                raise ValidationError(_("El PDF supera el límite configurado de %s MB.") % max_mb)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.name == _("Nuevo lote FEC"):
                record.name = "%s - %s" % (record.pdf_filename, fields.Datetime.now())
        return records

    def action_queue(self):
        for batch in self:
            if batch.state not in ("uploaded", "error"):
                raise UserError(_("Solo se pueden encolar lotes cargados o con error."))
            if not batch.privacy_accepted:
                raise UserError(_("Debe autorizar el envío del PDF a los proveedores de IA."))
            batch._prepare_metadata()
            batch.write({"state": "queued", "error_message": False})

    def action_process_now(self):
        self.ensure_one()
        if not self.privacy_accepted:
            raise UserError(_("Debe autorizar el envío del PDF a los proveedores de IA."))
        self._prepare_metadata()
        self._process_batch()
        return self.action_open_proposals()

    def action_discard(self):
        self.filtered(lambda b: b.state not in ("done",)).write({"state": "discarded"})

    def action_open_proposals(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "sng_ai_fec_digitizer.action_fec_proposal"
        )
        action["domain"] = [("batch_id", "=", self.id)]
        action["context"] = {"default_batch_id": self.id}
        return action

    @api.model
    def _cron_process_batches(self):
        batches = self.search([("state", "=", "queued")], limit=2, order="create_date")
        for batch in batches:
            try:
                with self.env.cr.savepoint():
                    batch._process_batch()
            except Exception as error:  # cron must continue with the next batch
                _logger.exception("Error procesando lote FEC IA %s", batch.id)
                batch.write({"state": "error", "error_message": str(error)[:4000]})

    def _get_config(self):
        self.ensure_one()
        icp = self.env["ir.config_parameter"].sudo()
        config = {
            "anthropic_key": icp.get_param("sng_ai_dashboard.api_key"),
            "anthropic_model": icp.get_param("sng_ai_dashboard.model") or "claude-opus-4-8",
            "deepseek_key": icp.get_param("sng_ai_dashboard.deepseek_api_key"),
            "deepseek_model": icp.get_param("sng_ai_dashboard.deepseek_model") or "deepseek-v4-flash",
            "deepseek_url": (icp.get_param("sng_ai_dashboard.deepseek_base_url") or "https://api.deepseek.com").rstrip("/"),
            "max_pages": int(icp.get_param("sng_ai_fec_digitizer.max_pages", 30)),
            "max_cost": float(icp.get_param("sng_ai_fec_digitizer.max_cost_usd", 5.0)),
        }
        if not config["anthropic_key"]:
            raise UserError(_("La digitalización visual requiere una API key de Anthropic."))
        if self.provider == "deepseek" and not config["deepseek_key"]:
            raise UserError(_("El flujo DeepSeek requiere las API keys de Anthropic y DeepSeek."))
        return config

    def _prepare_metadata(self):
        self.ensure_one()
        try:
            from PyPDF2 import PdfReader
        except ImportError as error:
            raise UserError(_("Falta la dependencia Python PyPDF2.")) from error
        config = self._get_config()
        try:
            pages = len(PdfReader(io.BytesIO(base64.b64decode(self.pdf_data))).pages)
        except Exception as error:
            raise UserError(_("No se pudo inspeccionar el PDF: %s") % error) from error
        if pages > config["max_pages"]:
            raise UserError(_("El PDF contiene %s páginas; el máximo es %s.") % (pages, config["max_pages"]))
        estimate = self._compute_cost(config["anthropic_model"], pages * 2000, 3000)
        if self.provider == "deepseek":
            estimate += self._compute_cost(config["deepseek_model"], pages * 1000, 3000)
        if config["max_cost"] and estimate > config["max_cost"]:
            raise UserError(_("El costo estimado $%.4f supera el límite $%.4f.") % (estimate, config["max_cost"]))
        values = {"page_count": pages, "estimated_cost_usd": estimate}
        if not self.privacy_accepted_at:
            values.update({"privacy_accepted_by": self.env.user.id, "privacy_accepted_at": fields.Datetime.now()})
        self.write(values)

    def _render_pages(self, pdf_bytes, max_pages):
        try:
            import pypdfium2 as pdfium
        except ImportError as error:
            raise UserError(_("Falta la dependencia Python pypdfium2.")) from error
        try:
            document = pdfium.PdfDocument(pdf_bytes)
        except Exception as error:
            raise UserError(_("No se pudo abrir el PDF: %s") % error) from error
        if len(document) > max_pages:
            raise UserError(_("El PDF contiene %s páginas; el máximo es %s.") % (len(document), max_pages))
        images = []
        for index in range(len(document)):
            image = document[index].render(scale=1.5).to_pil().convert("RGB")
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=82, optimize=True)
            images.append(output.getvalue())
        return images

    def _anthropic_extract(self, config, images):
        try:
            import anthropic
        except ImportError as error:
            raise UserError(_("Falta la dependencia Python anthropic.")) from error
        content = [{"type": "text", "text": EXTRACTION_PROMPT}]
        for index, image in enumerate(images, 1):
            content.extend([
                {"type": "text", "text": "Página %s:" % index},
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(image).decode()}},
            ])
        client = anthropic.Anthropic(api_key=config["anthropic_key"], timeout=300, max_retries=2)
        response = client.messages.create(
            model=config["anthropic_model"], max_tokens=12000,
            messages=[{"role": "user", "content": content}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return text, response.model, response.usage.input_tokens, response.usage.output_tokens

    def _deepseek_normalize(self, config, raw_text):
        try:
            response = requests.post(
                "%s/chat/completions" % config["deepseek_url"],
                headers={"Authorization": "Bearer %s" % config["deepseek_key"], "Content-Type": "application/json"},
                json={
                    "model": config["deepseek_model"], "max_tokens": 12000,
                    "thinking": {"type": "disabled"},
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "user", "content": NORMALIZATION_PROMPT % raw_text}],
                }, timeout=300,
            )
            response.raise_for_status()
            data = response.json()
            usage = data.get("usage") or {}
            return (data["choices"][0]["message"]["content"], data.get("model") or config["deepseek_model"],
                    usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
        except (requests.RequestException, ValueError, KeyError, IndexError) as error:
            raise UserError(_("DeepSeek no pudo normalizar la extracción: %s") % error) from error

    @api.model
    def _parse_json(self, text):
        clean = (text or "").strip()
        clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.I | re.S)
        try:
            data = json.loads(clean)
        except (TypeError, ValueError) as error:
            raise UserError(_("La IA devolvió JSON inválido.")) from error
        if not isinstance(data, dict) or not isinstance(data.get("documents"), list):
            raise UserError(_("La respuesta no contiene una lista 'documents' válida."))
        return data

    def _process_batch(self):
        self.ensure_one()
        if self.state not in ("uploaded", "queued", "error"):
            raise UserError(_("El lote no está disponible para procesamiento."))
        if self.proposal_ids:
            raise UserError(_("El lote ya contiene propuestas; descártelas antes de reprocesar."))
        config = self._get_config()
        self.write({"state": "processing", "attempt_count": self.attempt_count + 1, "error_message": False})
        try:
            pdf_bytes = base64.b64decode(self.pdf_data)
            images = self._render_pages(pdf_bytes, config["max_pages"])
            # Conservative preflight: vision commonly consumes roughly 2k tokens/page.
            estimated_cost = self._compute_cost(
                config["anthropic_model"], len(images) * 2000, 3000
            )
            if self.provider == "deepseek":
                estimated_cost += self._compute_cost(
                    config["deepseek_model"], len(images) * 1000, 3000
                )
            if config["max_cost"] and estimated_cost > config["max_cost"]:
                raise UserError(
                    _("El costo estimado $%.4f supera el límite $%.4f.")
                    % (estimated_cost, config["max_cost"])
                )
            raw, amodel, ain, aout = self._anthropic_extract(config, images)
            normalized, dmodel, din, dout = raw, False, 0, 0
            if self.provider == "deepseek":
                normalized, dmodel, din, dout = self._deepseek_normalize(config, raw)
            audit_response = json.dumps(
                {"anthropic_extraction": raw, "final_response": normalized},
                ensure_ascii=False,
            )
            self.raw_response = audit_response
            payload = self._parse_json(normalized)
            cost = self._compute_cost(amodel, ain, aout) + self._compute_cost(dmodel, din, dout)
            if config["max_cost"] and cost > config["max_cost"]:
                raise UserError(_("El costo calculado $%.4f supera el límite $%.4f.") % (cost, config["max_cost"]))
            commands = []
            for document in payload["documents"]:
                values = self.env["sng.ai.fec.proposal"]._values_from_ai(document, len(images))
                commands.append(Command.create(values))
            if not commands:
                raise UserError(_("La IA no detectó comprobantes en el PDF."))
            self.write({
                "proposal_ids": commands, "state": "review", "page_count": len(images),
                "anthropic_model": amodel, "anthropic_input_tokens": ain, "anthropic_output_tokens": aout,
                "deepseek_model": dmodel, "deepseek_input_tokens": din, "deepseek_output_tokens": dout,
                "cost_usd": cost, "raw_response": audit_response, "processed_at": fields.Datetime.now(),
            })
            for proposal in self.proposal_ids:
                proposal._match_partner_and_history()
                proposal._refresh_warnings()
        except Exception as error:
            self.write({"state": "error", "error_message": str(error)[:4000]})
            raise

    @api.model
    def _compute_cost(self, model, input_tokens, output_tokens):
        price_in, price_out = PRICING.get(model, (0.0, 0.0))
        return input_tokens / 1e6 * price_in + output_tokens / 1e6 * price_out
