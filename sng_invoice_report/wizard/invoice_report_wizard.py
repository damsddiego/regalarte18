import io
import base64
from datetime import date

from odoo import api, fields, models, _
from odoo.exceptions import UserError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class InvoiceReportWizard(models.TransientModel):
    _name = 'invoice.report.wizard'
    _description = 'Invoice Report by Salesperson Wizard'

    date_from = fields.Date(
        string='Date From',
        required=True,
        default=lambda self: date.today().replace(day=1),
    )
    date_to = fields.Date(
        string='Date To',
        required=True,
        default=fields.Date.context_today,
    )
    company_ids = fields.Many2many(
        'res.company',
        'invoice_report_wizard_company_rel',
        'wizard_id',
        'company_id',
        string='Companies',
        default=lambda self: self.env.companies.ids,
        help="Select companies to include in the report. Limited to your allowed companies.",
    )
    salesperson_ids = fields.Many2many(
        'res.partner',
        'invoice_report_wizard_salesperson_rel',
        'wizard_id',
        'partner_id',
        string='Salespersons',
        domain="[('is_salesperson', '=', True)]",
        help="Leave empty to include all salespersons",
    )
    invoice_type = fields.Selection([
        ('out_invoice', 'Customer Invoices'),
        ('out_refund', 'Customer Credit Notes'),
        ('all', 'All Customer Documents'),
    ], string='Invoice Type', default='out_invoice', required=True)

    payment_status = fields.Selection([
        ('all', 'All'),
        ('not_paid', 'Not Paid'),
        ('in_payment', 'In Payment'),
        ('paid', 'Paid'),
        ('partial', 'Partially Paid'),
        ('reversed', 'Reversed'),
    ], string='Payment Status', default='all', required=True)

    # Fields for Excel download
    excel_file = fields.Binary('Excel File', readonly=True)
    excel_filename = fields.Char('Excel Filename', readonly=True)
    line_ids = fields.One2many(
        'invoice.report.line',
        'wizard_id',
        string='Report Lines',
    )

    @api.model
    def default_get(self, fields_list):
        """Set default companies to user's allowed companies."""
        res = super().default_get(fields_list)
        if 'company_ids' in fields_list and not res.get('company_ids'):
            res['company_ids'] = self.env.companies.ids
        return res

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise UserError(_("'Date From' must be earlier than 'Date To'."))

    def _get_allowed_companies(self):
        """Return the companies allowed for this report run."""
        self.ensure_one()
        if self.company_ids:
            return self.company_ids & self.env.companies
        return self.env.companies

    def _get_report_domain(self, move_types=None):
        """Build the base domain for filtering report documents.

        Respects multi-company access rules by filtering on company_ids.
        Only returns documents from companies the user has access to.
        """
        self.ensure_one()
        domain = [
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('state', '=', 'posted'),
        ]

        allowed_companies = self._get_allowed_companies()
        if allowed_companies:
            domain.append(('company_id', 'in', allowed_companies.ids))
        else:
            domain.append(('id', '=', False))

        if move_types:
            if len(move_types) == 1:
                domain.append(('move_type', '=', move_types[0]))
            else:
                domain.append(('move_type', 'in', move_types))

        if self.payment_status != 'all':
            domain.append(('payment_state', '=', self.payment_status))

        return domain

    def _get_invoices_domain(self):
        """Keep the public invoice domain aligned with the report selection."""
        return [('id', 'in', self._get_report_moves().ids)]

    def _get_salesperson_rule_map(self, moves):
        """Return configured report salespersons keyed by company and user."""
        self.ensure_one()
        user_ids = moves.mapped('invoice_user_id').ids
        company_ids = moves.mapped('company_id').ids
        if not user_ids or not company_ids:
            return {}
        rules = self.env['invoice.report.salesperson.rule'].search([
            ('active', '=', True),
            ('company_id', 'in', company_ids),
            ('user_id', 'in', user_ids),
        ])
        return {
            (rule.company_id.id, rule.user_id.id): rule.salesperson_id
            for rule in rules
        }

    def _get_effective_salesperson(self, move, rule_map=None):
        """Return the configured report salesperson or the current fallback."""
        if rule_map is None:
            rule_map = self._get_salesperson_rule_map(move)
        configured_salesperson = rule_map.get(
            (move.company_id.id, move.invoice_user_id.id)
        )
        if configured_salesperson:
            return configured_salesperson
        return move.salesperson_id or move.assigned_salesperson_id

    def _filter_report_moves(self, moves, rule_map=None):
        """Apply post-search filters shared by screen and exports."""
        self.ensure_one()
        if rule_map is None:
            rule_map = self._get_salesperson_rule_map(moves)
        if self.salesperson_ids:
            salesperson_ids = set(self.salesperson_ids.ids)
            return moves.filtered(
                lambda move: self._get_effective_salesperson(move, rule_map).id
                in salesperson_ids
            )
        return moves.filtered(
            lambda move: not self._get_effective_salesperson(move, rule_map)
            or self._get_effective_salesperson(move, rule_map).is_salesperson
        )

    def _sort_report_moves(self, moves, rule_map=None):
        """Sort moves using the report grouping logic."""
        if rule_map is None:
            rule_map = self._get_salesperson_rule_map(moves)
        return moves.sorted(
            key=lambda move: (
                (self._get_effective_salesperson(move, rule_map).id or 0),
                move.invoice_date or date.min,
                move.move_type == 'out_refund',
                move.name or '',
                move.id,
            )
        )

    def _get_report_move_sets(self):
        """Return the invoices and refunds that belong to the report."""
        self.ensure_one()
        move_model = self.env['account.move']

        if self.invoice_type == 'out_refund':
            invoices = move_model.browse()
            refunds = move_model.search(
                self._get_report_domain(move_types=['out_refund']),
                order='salesperson_id, invoice_date, name, id',
            )
        elif self.invoice_type == 'all':
            invoices = move_model.search(
                self._get_report_domain(move_types=['out_invoice']),
                order='salesperson_id, invoice_date, name, id',
            )
            refunds = move_model.search(
                self._get_report_domain(move_types=['out_refund']),
                order='salesperson_id, invoice_date, name, id',
            )
        else:
            invoices = move_model.search(
                self._get_report_domain(move_types=['out_invoice']),
                order='salesperson_id, invoice_date, name, id',
            )
            refunds = move_model.search(
                self._get_report_domain(move_types=['out_refund']),
                order='salesperson_id, invoice_date, name, id',
            )

        rule_map = self._get_salesperson_rule_map(invoices | refunds)
        return (
            self._filter_report_moves(invoices, rule_map),
            self._filter_report_moves(refunds, rule_map),
        )

    def _get_report_moves(self):
        """Return all unique moves included in the report."""
        invoices, refunds = self._get_report_move_sets()
        return self._sort_report_moves(invoices | refunds)

    def _get_salesperson_bucket(self, data_by_salesperson, move, rule_map=None):
        """Get or create the aggregation bucket for a move salesperson."""
        salesperson = self._get_effective_salesperson(move, rule_map)
        salesperson_id = salesperson.id if salesperson else False
        salesperson_name = salesperson.name if salesperson else 'Sin asignar'

        if salesperson_id not in data_by_salesperson:
            data_by_salesperson[salesperson_id] = {
                'salesperson_name': salesperson_name,
                'salesperson_id': salesperson_id,
                'invoices': [],
                'totals_by_currency': {},
                'totals_crc': {'untaxed': 0.0, 'tax': 0.0, 'subtotal': 0.0, 'total': 0.0},
            }
        return data_by_salesperson[salesperson_id]

    def _get_totals_bucket(self, totals_by_currency, currency):
        """Get or create totals bucket for a specific document currency."""
        currency_id = currency.id if currency else False
        currency_name = currency.name if currency else _('No Currency')

        if currency_id not in totals_by_currency:
            totals_by_currency[currency_id] = {
                'currency_id': currency_id,
                'currency': currency_name,
                'untaxed': 0.0,
                'tax': 0.0,
                'total': 0.0,
            }
        return totals_by_currency[currency_id]

    def _serialize_totals_by_currency(self, totals_by_currency):
        """Return currency totals sorted by currency label for rendering."""
        return sorted(
            totals_by_currency.values(),
            key=lambda total_data: (
                total_data['currency'] or '',
                total_data['currency_id'] or 0,
            ),
        )

    def _prepare_move_line(self, move, display_name=None):
        """Build a report line preserving the current visual design."""
        is_credit_note = move.move_type == 'out_refund'
        sign = -1 if is_credit_note else 1
        return {
            'number': display_name or move.name,
            'date': str(move.invoice_date) if move.invoice_date else '',
            'partner': move.partner_id.name,
            'partner_vat': move.partner_id.vat or '',
            'currency': move.currency_id.name,
            'company': move.company_id.name,
            'amount_untaxed': sign * abs(move.amount_untaxed),
            'amount_tax': sign * abs(move.amount_tax),
            'amount_total': sign * abs(move.amount_total),
            'amount_untaxed_crc': sign * abs(move.amount_untaxed_signed),
            'amount_tax_crc': sign * abs(move.amount_tax_signed),
            'amount_total_crc': sign * abs(move.amount_total_signed),
            'amount_subtotal_crc': sign * abs(move.amount_untaxed_signed),
            'move_type': dict(move._fields['move_type'].selection).get(move.move_type),
            'payment_state': move.payment_state,
            'is_reversal_line': is_credit_note,
        }

    def _append_move_line(self, bucket, move, grand_totals_by_currency, grand_totals_crc, display_name=None):
        """Append a move to salesperson and grand totals."""
        line = self._prepare_move_line(move, display_name=display_name)
        bucket['invoices'].append(line)
        bucket_totals = self._get_totals_bucket(bucket['totals_by_currency'], move.currency_id)
        bucket_totals['untaxed'] += line['amount_untaxed']
        bucket_totals['tax'] += line['amount_tax']
        bucket_totals['total'] += line['amount_total']

        # CRC totals (company currency)
        bucket['totals_crc']['untaxed'] += line['amount_untaxed_crc']
        bucket['totals_crc']['tax'] += line['amount_tax_crc']
        bucket['totals_crc']['subtotal'] += line['amount_subtotal_crc']
        bucket['totals_crc']['total'] += line['amount_total_crc']

        grand_totals = self._get_totals_bucket(grand_totals_by_currency, move.currency_id)
        grand_totals['untaxed'] += line['amount_untaxed']
        grand_totals['tax'] += line['amount_tax']
        grand_totals['total'] += line['amount_total']

        grand_totals_crc['untaxed'] += line['amount_untaxed_crc']
        grand_totals_crc['tax'] += line['amount_tax_crc']
        grand_totals_crc['subtotal'] += line['amount_subtotal_crc']
        grand_totals_crc['total'] += line['amount_total_crc']

    def _get_report_data(self):
        """Prepare data for the report grouped by salesperson.

        Handles multi-company reporting and correctly processes credit notes
        to avoid double-counting reversals.
        """
        invoices, refunds = self._get_report_move_sets()
        report_moves = invoices | refunds

        if not report_moves:
            raise UserError(_("No invoices found with the selected filters."))

        # Group invoices by salesperson
        data_by_salesperson = {}
        grand_totals_by_currency = {}
        grand_totals_crc = {'untaxed': 0.0, 'tax': 0.0, 'subtotal': 0.0, 'total': 0.0}

        # Get company names for display
        company_names = ', '.join(self.company_ids.mapped('name')) if len(self.company_ids) > 1 else (
            self.company_ids.name if self.company_ids else self.env.company.name
        )

        refunds_by_parent = {}
        rule_map = self._get_salesperson_rule_map(report_moves)

        for refund in self._sort_report_moves(refunds, rule_map):
            parent_id = refund.reversed_entry_id.id
            if parent_id:
                refunds_by_parent.setdefault(parent_id, self.env['account.move'].browse())
                refunds_by_parent[parent_id] |= refund

        processed_refund_ids = set()

        for invoice in self._sort_report_moves(invoices, rule_map):
            bucket = self._get_salesperson_bucket(data_by_salesperson, invoice, rule_map)
            self._append_move_line(bucket, invoice, grand_totals_by_currency, grand_totals_crc)

            linked_refunds = refunds_by_parent.get(invoice.id, self.env['account.move'].browse())
            for refund in self._sort_report_moves(
                linked_refunds.filtered(lambda move: move.id not in processed_refund_ids),
                rule_map,
            ):
                self._append_move_line(bucket, refund, grand_totals_by_currency, grand_totals_crc, display_name=f"↳ {refund.name}")
                processed_refund_ids.add(refund.id)

        remaining_refunds = refunds.filtered(lambda move: move.id not in processed_refund_ids)
        for refund in self._sort_report_moves(remaining_refunds, rule_map):
            bucket = self._get_salesperson_bucket(data_by_salesperson, refund, rule_map)
            self._append_move_line(bucket, refund, grand_totals_by_currency, grand_totals_crc)
            processed_refund_ids.add(refund.id)

        return {
            'date_from': str(self.date_from),
            'date_to': str(self.date_to),
            'data_by_salesperson': [
                {
                    **bucket,
                    'totals_by_currency': self._serialize_totals_by_currency(bucket['totals_by_currency']),
                }
                for bucket in data_by_salesperson.values()
            ],
            'grand_totals_by_currency': self._serialize_totals_by_currency(grand_totals_by_currency),
            'grand_totals_crc': grand_totals_crc,
            'company': self.env.company,
            'company_names': company_names,
            'companies_count': len(self.company_ids) if self.company_ids else 1,
            'invoice_count': len(report_moves),
        }

    def action_view_on_screen(self):
        """Build temporary lines so on-screen grouping matches exports."""
        self.ensure_one()
        report_moves = self._get_report_moves()
        rule_map = self._get_salesperson_rule_map(report_moves)
        move_type_selection = dict(self.env['account.move']._fields['move_type'].selection)
        payment_state_selection = dict(self.env['account.move']._fields['payment_state'].selection)
        self.line_ids.unlink()
        values_list = []
        for move in self._sort_report_moves(report_moves, rule_map):
            line = self._prepare_move_line(move)
            salesperson = self._get_effective_salesperson(move, rule_map)
            values_list.append({
                'wizard_id': self.id,
                'move_id': move.id,
                'invoice_date': move.invoice_date,
                'partner_id': move.partner_id.id,
                'company_id': move.company_id.id,
                'currency_id': move.currency_id.id,
                'company_currency_id': move.company_currency_id.id,
                'invoice_user_id': move.invoice_user_id.id,
                'original_salesperson_id': move.salesperson_id.id,
                'salesperson_id': salesperson.id,
                'move_type': move_type_selection.get(move.move_type, move.move_type),
                'payment_state': payment_state_selection.get(move.payment_state, move.payment_state),
                'amount_untaxed': line['amount_untaxed'],
                'amount_tax': line['amount_tax'],
                'amount_total': line['amount_total'],
                'amount_untaxed_company': line['amount_untaxed_crc'],
                'amount_tax_company': line['amount_tax_crc'],
                'amount_total_company': line['amount_total_crc'],
            })
        if values_list:
            self.env['invoice.report.line'].create(values_list)

        # Reading an action record directly requires Settings access. Elevate only
        # this static UI metadata; report data keeps the current user's permissions.
        action = self.env.ref(
            'sng_invoice_report.action_invoice_report_line'
        ).sudo().read()[0]
        action.update({
            'name': _('Invoice Report: %(date_from)s to %(date_to)s',
                      date_from=self.date_from, date_to=self.date_to),
            'domain': [('wizard_id', '=', self.id)],
        })
        return action

    def action_print_pdf(self):
        """Generate and download PDF report."""
        self.ensure_one()
        data = self._get_report_data()
        # Remove company object - it cannot be serialized properly
        if 'company' in data:
            del data['company']
        return self.env.ref('sng_invoice_report.action_report_invoice_salesperson').report_action(self, data=data)

    def action_print_excel(self):
        """Generate and download Excel report."""
        self.ensure_one()

        if not xlsxwriter:
            raise UserError(_("The 'xlsxwriter' Python library is required. Please install it with: pip install xlsxwriter"))

        data = self._get_report_data()

        # Create Excel file in memory
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet(_('Invoice Report')[:31])

        # Define formats
        title_format = workbook.add_format({
            'bold': True,
            'font_size': 16,
            'align': 'center',
            'valign': 'vcenter',
        })
        header_format = workbook.add_format({
            'bold': True,
            'font_size': 11,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#4472C4',
            'font_color': 'white',
            'border': 1,
        })
        salesperson_format = workbook.add_format({
            'bold': True,
            'font_size': 12,
            'bg_color': '#D9E2F3',
            'border': 1,
        })
        cell_format = workbook.add_format({
            'font_size': 10,
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
        })
        number_format = workbook.add_format({
            'font_size': 10,
            'align': 'right',
            'valign': 'vcenter',
            'num_format': '#,##0.00',
            'border': 1,
        })
        date_format = workbook.add_format({
            'font_size': 10,
            'align': 'center',
            'valign': 'vcenter',
            'num_format': 'yyyy-mm-dd',
            'border': 1,
        })
        # Red formats for reversed invoices
        cell_format_red = workbook.add_format({
            'font_size': 10,
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'font_color': 'red',
        })
        number_format_red = workbook.add_format({
            'font_size': 10,
            'align': 'right',
            'valign': 'vcenter',
            'num_format': '#,##0.00',
            'border': 1,
            'font_color': 'red',
        })
        date_format_red = workbook.add_format({
            'font_size': 10,
            'align': 'center',
            'valign': 'vcenter',
            'num_format': 'yyyy-mm-dd',
            'border': 1,
            'font_color': 'red',
        })
        # Gray italic formats for reversal/credit note lines
        cell_format_reversal = workbook.add_format({
            'font_size': 10,
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'font_color': '#666666',
            'italic': True,
        })
        number_format_reversal = workbook.add_format({
            'font_size': 10,
            'align': 'right',
            'valign': 'vcenter',
            'num_format': '#,##0.00',
            'border': 1,
            'font_color': '#666666',
            'italic': True,
        })
        date_format_reversal = workbook.add_format({
            'font_size': 10,
            'align': 'center',
            'valign': 'vcenter',
            'num_format': 'yyyy-mm-dd',
            'border': 1,
            'font_color': '#666666',
            'italic': True,
        })
        subtotal_format = workbook.add_format({
            'bold': True,
            'font_size': 10,
            'align': 'right',
            'valign': 'vcenter',
            'num_format': '#,##0.00',
            'bg_color': '#E2EFDA',
            'border': 1,
        })
        subtotal_label_format = workbook.add_format({
            'bold': True,
            'font_size': 10,
            'align': 'right',
            'valign': 'vcenter',
            'bg_color': '#E2EFDA',
            'border': 1,
        })
        grand_total_format = workbook.add_format({
            'bold': True,
            'font_size': 11,
            'align': 'right',
            'valign': 'vcenter',
            'num_format': '#,##0.00',
            'bg_color': '#FFC000',
            'border': 2,
        })
        grand_total_label_format = workbook.add_format({
            'bold': True,
            'font_size': 11,
            'align': 'right',
            'valign': 'vcenter',
            'bg_color': '#FFC000',
            'border': 2,
        })

        # Determine if we show company column
        show_company = data['companies_count'] > 1
        num_cols = 12 if show_company else 11
        last_col = num_cols - 1

        # Set column widths
        worksheet.set_column('A:A', 18)  # Invoice Number
        worksheet.set_column('B:B', 12)  # Date
        worksheet.set_column('C:C', 35)  # Customer
        worksheet.set_column('D:D', 15)  # VAT
        if show_company:
            worksheet.set_column('E:E', 20)  # Company
            worksheet.set_column('F:F', 18)  # Type
            worksheet.set_column('G:G', 8)   # Currency
            worksheet.set_column('H:H', 15)  # Untaxed Amount
            worksheet.set_column('I:I', 12)  # Tax
            worksheet.set_column('J:J', 15)  # Total
            worksheet.set_column('K:K', 15)  # Subtotal (CRC)
            worksheet.set_column('L:L', 15)  # Total (CRC)
        else:
            worksheet.set_column('E:E', 18)  # Type
            worksheet.set_column('F:F', 8)   # Currency
            worksheet.set_column('G:G', 15)  # Untaxed Amount
            worksheet.set_column('H:H', 12)  # Tax
            worksheet.set_column('I:I', 15)  # Total
            worksheet.set_column('J:J', 15)  # Subtotal (CRC)
            worksheet.set_column('K:K', 15)  # Total (CRC)

        row = 0

        # Title
        worksheet.merge_range(
            row, 0, row, last_col,
            _('Invoice Report by Salesperson'),
            title_format,
        )
        row += 1
        worksheet.merge_range(
            row, 0, row, last_col,
            _(
                '%(companies)s - From %(date_from)s to %(date_to)s',
                companies=data['company_names'],
                date_from=data['date_from'],
                date_to=data['date_to'],
            ),
            workbook.add_format({'align': 'center', 'font_size': 11}),
        )
        row += 2

        # Headers
        if show_company:
            headers = [
                _('Invoice #'),
                _('Date'),
                _('Customer'),
                _('VAT'),
                _('Company'),
                _('Type'),
                _('Currency'),
                _('Untaxed'),
                _('Tax'),
                _('Total'),
                _('Subtotal (CRC)'),
                _('Total (CRC)'),
            ]
        else:
            headers = [
                _('Invoice #'),
                _('Date'),
                _('Customer'),
                _('VAT'),
                _('Type'),
                _('Currency'),
                _('Untaxed'),
                _('Tax'),
                _('Total'),
                _('Subtotal (CRC)'),
                _('Total (CRC)'),
            ]
        for col, header in enumerate(headers):
            worksheet.write(row, col, header, header_format)
        row += 1

        # Data by salesperson
        for sp_data in data['data_by_salesperson']:
            # Salesperson header
            worksheet.merge_range(
                row, 0, row, last_col,
                _('Salesperson: %(name)s', name=sp_data['salesperson_name']),
                salesperson_format,
            )
            row += 1

            # Invoice lines
            for inv in sp_data['invoices']:
                # Determine format based on invoice state
                is_reversed = inv.get('payment_state') == 'reversed'
                is_reversal_line = inv.get('is_reversal_line', False)

                if is_reversal_line:
                    # Gray italic for credit note lines
                    cf = cell_format_reversal
                    df = date_format_reversal
                    nf = number_format_reversal
                elif is_reversed:
                    # Red for reversed invoices
                    cf = cell_format_red
                    df = date_format_red
                    nf = number_format_red
                else:
                    # Normal format
                    cf = cell_format
                    df = date_format
                    nf = number_format

                col = 0
                worksheet.write(row, col, inv['number'], cf)
                col += 1
                worksheet.write(row, col, str(inv['date']), df)
                col += 1
                worksheet.write(row, col, inv['partner'], cf)
                col += 1
                worksheet.write(row, col, inv['partner_vat'], cf)
                col += 1
                if show_company:
                    worksheet.write(row, col, inv.get('company', ''), cf)
                    col += 1
                worksheet.write(row, col, inv['move_type'], cf)
                col += 1
                worksheet.write(row, col, inv['currency'], cf)
                col += 1
                worksheet.write(row, col, inv['amount_untaxed'], nf)
                col += 1
                worksheet.write(row, col, inv['amount_tax'], nf)
                col += 1
                worksheet.write(row, col, inv['amount_total'], nf)
                col += 1
                worksheet.write(row, col, inv['amount_subtotal_crc'], nf)
                col += 1
                worksheet.write(row, col, inv['amount_total_crc'], nf)
                row += 1

            # Subtotal row in CRC
            # Columns: ... Total | Subtotal(CRC) | Total(CRC)
            # Last 4 columns are: untaxed | tax | subtotal | total (all CRC)
            totals_crc = sp_data.get('totals_crc', {})
            worksheet.merge_range(
                row, 0, row, num_cols - 5,
                _('Subtotal - %(name)s (CRC)', name=sp_data['salesperson_name']),
                subtotal_label_format,
            )
            worksheet.write(row, num_cols - 4, totals_crc.get('untaxed', 0.0), subtotal_format)
            worksheet.write(row, num_cols - 3, totals_crc.get('tax', 0.0), subtotal_format)
            worksheet.write(row, num_cols - 2, totals_crc.get('subtotal', 0.0), subtotal_format)
            worksheet.write(row, num_cols - 1, totals_crc.get('total', 0.0), subtotal_format)
            row += 2

        # Grand total in CRC
        grand_totals_crc = data.get('grand_totals_crc', {})
        worksheet.merge_range(
            row, 0, row, num_cols - 5,
            _('GRAND TOTAL (CRC)'),
            grand_total_label_format,
        )
        worksheet.write(row, num_cols - 4, grand_totals_crc.get('untaxed', 0.0), grand_total_format)
        worksheet.write(row, num_cols - 3, grand_totals_crc.get('tax', 0.0), grand_total_format)
        worksheet.write(row, num_cols - 2, grand_totals_crc.get('subtotal', 0.0), grand_total_format)
        worksheet.write(row, num_cols - 1, grand_totals_crc.get('total', 0.0), grand_total_format)
        row += 1

        workbook.close()
        output.seek(0)

        # Save the file to the wizard
        filename = f"invoice_report_{self.date_from}_{self.date_to}.xlsx"
        self.write({
            'excel_file': base64.b64encode(output.getvalue()),
            'excel_filename': filename,
        })

        # Return action to download
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self._name}/{self.id}/excel_file/{filename}?download=true',
            'target': 'new',
        }
