# -*- coding: utf-8 -*-

import base64
import re
import unicodedata
from datetime import date
from io import BytesIO

from openpyxl import load_workbook

from odoo import _, api, fields, models
from odoo.exceptions import UserError

HEADER_SCAN_ROWS = 30
CODE_HEADERS = {'CODIGO', 'COD', 'CODCLIE', 'CODIGOCLIENTE'}
NAME_HEADER_PREFIXES = ('CLIENTE', 'NOMBRE')


def _normalize_text(value):
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode()
    return re.sub(r'[^A-Z0-9]', '', text.upper())


def _normalize_code(value):
    if value in (None, ''):
        return False
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    code = str(value).strip()
    if code.isdigit():
        return code.zfill(5)
    return code or False


class SngCommercialPlanHistoryImportWizard(models.TransientModel):
    _name = 'sng.commercial.plan.history.import.wizard'
    _description = 'Importar Venta Historica Plan Comercial'

    @api.model
    def _default_date_from(self):
        return date(fields.Date.context_today(self).year - 1, 1, 1)

    @api.model
    def _default_date_to(self):
        return date(fields.Date.context_today(self).year - 1, 12, 31)

    company_id = fields.Many2one(
        'res.company',
        string='Compania',
        required=True,
        default=lambda self: self.env.company,
    )
    file_data = fields.Binary(string='Archivo Excel', required=True)
    file_name = fields.Char(string='Nombre Archivo')
    date_from = fields.Date(string='Periodo Desde', required=True, default=_default_date_from)
    date_to = fields.Date(string='Periodo Hasta', required=True, default=_default_date_to)
    amount_column = fields.Char(
        string='Columna de Venta',
        required=True,
        default='Ventas Netas IVAI',
        help='Encabezado de la columna con la venta neta. El plan compara contra '
             'amount_total_signed de las facturas, que incluye IVA.',
    )
    replace_existing = fields.Boolean(
        string='Reemplazar historico del mismo periodo',
        default=True,
    )
    state = fields.Selection(
        selection=[('draft', 'Borrador'), ('done', 'Listo')],
        default='draft',
        readonly=True,
    )
    result_message = fields.Text(string='Resultado', readonly=True)

    def action_import(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('La fecha inicial no puede superar la fecha final.'))
        rows = self._read_rows()
        if not rows:
            raise UserError(_('El archivo no tiene filas con codigo de cliente y venta.'))

        history_model = self.env['sng.commercial.plan.history']
        same_period = history_model.search([
            ('company_id', '=', self.company_id.id),
            ('date_from', '=', self.date_from),
            ('date_to', '=', self.date_to),
        ])
        if same_period and not self.replace_existing:
            raise UserError(_(
                'Ya existe venta historica para este periodo. Marque "Reemplazar historico '
                'del mismo periodo" o elimine las filas existentes.'
            ))

        previous_assignments = self._get_previous_assignments()
        matcher = self._build_partner_matcher()
        vals_list = []
        for code, name, amount in rows:
            partner, method, note = self._match_partner(code, name, previous_assignments, matcher)
            vals_list.append({
                'company_id': self.company_id.id,
                'date_from': self.date_from,
                'date_to': self.date_to,
                'source_code': code,
                'source_name': name,
                'amount': amount,
                'partner_id': partner.id if partner else False,
                'match_method': method,
                'note': note,
                'source_file': self.file_name,
            })

        same_period.unlink()
        history_model.create(vals_list)
        self.write({
            'state': 'done',
            'result_message': self._build_result_message(vals_list),
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Importar Venta Historica'),
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def action_open_history(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'sng_plan_comercial_clientes.action_sng_commercial_plan_history'
        )
        action['domain'] = [
            ('company_id', '=', self.company_id.id),
            ('date_from', '=', self.date_from),
            ('date_to', '=', self.date_to),
        ]
        action['context'] = {'search_default_filter_unassigned': 1}
        return action

    def _read_rows(self):
        try:
            workbook = load_workbook(
                BytesIO(base64.b64decode(self.file_data)),
                data_only=True,
                read_only=True,
            )
        except Exception as error:
            raise UserError(_('No se pudo leer el archivo Excel: %s') % error) from error

        amount_header = _normalize_text(self.amount_column)
        for worksheet in workbook.worksheets:
            sheet_rows = list(worksheet.iter_rows(values_only=True))
            columns = self._find_columns(sheet_rows, amount_header)
            if columns:
                return self._extract_rows(sheet_rows, *columns)
        raise UserError(_(
            'No se encontro una hoja con las columnas "Codigo", "Cliente" y "%s" en las '
            'primeras %s filas.'
        ) % (self.amount_column, HEADER_SCAN_ROWS))

    def _find_columns(self, sheet_rows, amount_header):
        for header_index, row in enumerate(sheet_rows[:HEADER_SCAN_ROWS]):
            normalized = [_normalize_text(cell) for cell in row]
            code_col = next((i for i, cell in enumerate(normalized) if cell in CODE_HEADERS), None)
            amount_col = next((i for i, cell in enumerate(normalized) if cell == amount_header), None)
            name_col = next(
                (i for i, cell in enumerate(normalized) if cell.startswith(NAME_HEADER_PREFIXES)),
                None,
            )
            if code_col is not None and amount_col is not None:
                return header_index, code_col, name_col, amount_col
        return None

    def _extract_rows(self, sheet_rows, header_index, code_col, name_col, amount_col):
        totals = {}
        names = {}
        for row in sheet_rows[header_index + 1:]:
            if len(row) <= max(code_col, amount_col):
                continue
            code = _normalize_code(row[code_col])
            amount = row[amount_col]
            if not code or not isinstance(amount, (int, float)):
                continue
            totals[code] = totals.get(code, 0.0) + amount
            if name_col is not None and row[name_col] and code not in names:
                names[code] = str(row[name_col]).strip()
        return [(code, names.get(code, ''), totals[code]) for code in totals]

    def _get_previous_assignments(self):
        records = self.env['sng.commercial.plan.history'].search([
            ('company_id', '=', self.company_id.id),
            ('match_method', 'in', ('manual', 'history')),
            ('partner_id', '!=', False),
            ('source_code', '!=', False),
        ], order='id desc')
        assignments = {}
        for record in records:
            assignments.setdefault(record.source_code, record.partner_id)
        return assignments

    def _build_partner_matcher(self):
        partner_model = self.env['res.partner'].with_context(active_test=False)
        partners = partner_model.search([
            ('parent_id', '=', False),
            ('company_id', 'in', (False, self.company_id.id)),
        ])
        by_code = {}
        by_name = {}
        has_code = 'unique_id' in partner_model._fields
        has_commercial_name = 'commercial_name' in partner_model._fields
        for partner in partners:
            if has_code and partner.unique_id:
                by_code.setdefault(_normalize_code(partner.unique_id), partner_model)
                by_code[_normalize_code(partner.unique_id)] |= partner
            names = {_normalize_text(partner.name)}
            if has_commercial_name and partner.commercial_name:
                names.add(_normalize_text(partner.commercial_name))
            for name in names - {''}:
                by_name.setdefault(name, partner_model)
                by_name[name] |= partner
        return by_code, by_name

    def _match_partner(self, code, name, previous_assignments, matcher):
        by_code, by_name = matcher
        if code in previous_assignments:
            return previous_assignments[code], 'history', False

        normalized_name = _normalize_text(name)
        candidates = by_code.get(code)
        if candidates:
            if len(candidates) == 1:
                return candidates, 'code', False
            same_name = candidates & by_name.get(normalized_name, candidates.browse())
            if len(same_name) == 1:
                return same_name, 'code', False
            # El codigo de cliente se repite con proveedores de la misma numeracion.
            customers_only = candidates.filtered(
                lambda partner: partner.customer_rank > 0 and not partner.supplier_rank
            )
            if len(customers_only) == 1:
                return customers_only, 'code', _('Codigo repetido, se eligio el unico cliente sin rol de proveedor.')
            return False, 'none', _('Codigo repetido en: %s') % ', '.join(candidates.mapped('display_name'))

        same_name = by_name.get(normalized_name)
        if same_name and len(same_name) == 1:
            return same_name, 'name', _('Sin codigo en Odoo, asignado por nombre.')
        return False, 'none', _('No se encontro el cliente por codigo ni por nombre.')

    def _build_result_message(self, vals_list):
        def total(method):
            return sum(vals['amount'] for vals in vals_list if vals['match_method'] == method)

        def count(method):
            return sum(1 for vals in vals_list if vals['match_method'] == method)

        lines = [
            _('Periodo: %(from)s - %(to)s') % {
                'from': self.date_from.strftime('%d/%m/%Y'),
                'to': self.date_to.strftime('%d/%m/%Y'),
            },
            _('Filas importadas: %(count)s por %(amount)s') % {
                'count': len(vals_list),
                'amount': '{:,.2f}'.format(sum(vals['amount'] for vals in vals_list)),
            },
            _('Asignadas por codigo: %s') % count('code'),
            _('Asignadas por nombre: %s') % count('name'),
            _('Asignacion previa reutilizada: %s') % count('history'),
        ]
        if count('none'):
            lines.append(_(
                'Sin asignar: %(count)s por %(amount)s. Asigne el cliente en Venta Historica; '
                'no cuentan en el plan hasta tener cliente.'
            ) % {'count': count('none'), 'amount': '{:,.2f}'.format(total('none'))})
        return '\n'.join(lines)
