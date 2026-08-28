# -*- coding: utf-8 -*-
import base64
import io
import re

from odoo import api, fields, models, _
from odoo.exceptions import UserError


def _eval_quantity(value):
    """Evalúa una cantidad que puede ser un número o una fórmula simple como =1+1+1."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if s.startswith("="):
        s = s[1:]
    # Solo permitir dígitos, espacios y operadores aritméticos básicos
    if re.fullmatch(r"[\d\s\+\-\*\/\.]+", s):
        try:
            return float(eval(s))  # noqa: S307 — entrada ya validada con regex
        except Exception:
            pass
    return 0.0


class SngScrapImportLine(models.TransientModel):
    _name = "sng.scrap.import.line"
    _description = "Línea de importación de desechos"

    wizard_id = fields.Many2one("sng.scrap.import.wizard", ondelete="cascade")
    product_code = fields.Char(string="Código")
    product_description = fields.Char(string="Descripción Excel")
    product_id = fields.Many2one("product.product", string="Producto")
    qty = fields.Float(string="Cantidad", digits="Product Unit of Measure")
    warning = fields.Char(string="Advertencia")
    state = fields.Selection(
        [("ok", "OK"), ("warning", "Advertencia"), ("error", "Error")],
        default="ok",
    )


class SngScrapImportWizard(models.TransientModel):
    _name = "sng.scrap.import.wizard"
    _description = "Importar Desechos desde Excel"

    state = fields.Selection(
        [("upload", "Cargar Archivo"), ("preview", "Previsualizar"), ("done", "Listo")],
        default="upload",
    )
    file_data = fields.Binary(string="Archivo Excel", required=True)
    file_name = fields.Char(string="Nombre del archivo")
    location_id = fields.Many2one(
        "stock.location",
        string="Ubicación origen",
        required=True,
        domain=[("usage", "in", ["internal", "transit"])],
    )
    scrap_location_id = fields.Many2one(
        "stock.location",
        string="Ubicación de desecho",
        domain=[("scrap_location", "=", True)],
    )
    auto_validate = fields.Boolean(
        string="Validar desechos automáticamente",
        default=False,
        help="Si está marcado, los desechos se validan al importar.",
    )
    line_ids = fields.One2many("sng.scrap.import.line", "wizard_id", string="Líneas")

    # Contadores para el resumen
    count_ok = fields.Integer(compute="_compute_counts")
    count_warning = fields.Integer(compute="_compute_counts")
    count_error = fields.Integer(compute="_compute_counts")

    @api.depends("line_ids.state")
    def _compute_counts(self):
        for rec in self:
            rec.count_ok = len(rec.line_ids.filtered(lambda l: l.state == "ok"))
            rec.count_warning = len(rec.line_ids.filtered(lambda l: l.state == "warning"))
            rec.count_error = len(rec.line_ids.filtered(lambda l: l.state == "error"))

    def action_load_preview(self):
        self.ensure_one()
        if not self.file_data:
            raise UserError(_("Por favor suba un archivo Excel."))

        try:
            import openpyxl
        except ImportError:
            raise UserError(_("La librería openpyxl no está instalada en el servidor."))

        file_bytes = base64.b64decode(self.file_data)
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        except Exception as e:
            raise UserError(_("No se pudo leer el archivo Excel: %s") % str(e))

        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            raise UserError(_("El archivo está vacío."))

        # Detectar fila de encabezado (busca 'Codigo' en cualquiera de las primeras 3 filas)
        header_row = 0
        for i, row in enumerate(rows[:3]):
            row_lower = [str(c).lower().strip() if c else "" for c in row]
            if any("codigo" in c or "código" in c for c in row_lower):
                header_row = i
                break

        data_rows = rows[header_row + 1:]

        # Limpiar líneas previas
        self.line_ids.unlink()

        lines = []
        for row in data_rows:
            if not any(row):
                continue
            code = str(row[0]).strip() if row[0] is not None else ""
            description = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
            raw_qty = row[2] if len(row) > 2 else 0
            qty = _eval_quantity(raw_qty)

            if not code:
                continue

            product = self.env["product.product"].search(
                [("default_code", "=", code)], limit=1
            )

            if qty <= 0:
                state = "error"
                warning = _("Cantidad inválida: %s") % raw_qty
                product_id = product.id if product else False
            elif not product:
                state = "warning"
                warning = _("Producto no encontrado con código '%s'") % code
                product_id = False
            else:
                state = "ok"
                warning = ""
                product_id = product.id

            lines.append({
                "wizard_id": self.id,
                "product_code": code,
                "product_description": description,
                "product_id": product_id,
                "qty": qty,
                "warning": warning,
                "state": state,
            })

        if not lines:
            raise UserError(_("No se encontraron filas de datos en el archivo."))

        self.env["sng.scrap.import.line"].create(lines)
        self.state = "preview"

        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_import_scraps(self):
        self.ensure_one()
        importable = self.line_ids.filtered(lambda l: l.state == "ok" and l.product_id and l.qty > 0)
        if not importable:
            raise UserError(_("No hay líneas válidas para importar. Corrija los errores primero."))

        # Ubicación de desecho por defecto si no se especificó
        scrap_location = self.scrap_location_id
        if not scrap_location:
            scrap_location = self.env["stock.location"].search(
                [("scrap_location", "=", True), ("active", "=", True)], limit=1
            )
            if not scrap_location:
                raise UserError(_("No se encontró una ubicación de desecho configurada."))

        scraps_created = self.env["stock.scrap"]
        for line in importable:
            scrap = self.env["stock.scrap"].create({
                "product_id": line.product_id.id,
                "product_uom_id": line.product_id.uom_id.id,
                "scrap_qty": line.qty,
                "location_id": self.location_id.id,
                "scrap_location_id": scrap_location.id,
            })
            scraps_created |= scrap
            if self.auto_validate:
                scrap.action_validate()

        self.state = "done"

        # Abrir los desechos creados
        action = self.env.ref("stock.action_stock_scrap").read()[0]
        action["domain"] = [("id", "in", scraps_created.ids)]
        action["context"] = {}
        return action

    def action_back(self):
        self.state = "upload"
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
