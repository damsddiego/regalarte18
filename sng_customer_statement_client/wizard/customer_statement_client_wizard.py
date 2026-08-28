# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import date

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class CustomerStatementClientWizard(models.TransientModel):
    _name = 'sng.customer.statement.client.wizard'
    _description = 'Asistente: Estado de Cuenta para Cliente'

    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
        domain="[('customer_rank', '>', 0)]",
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
    )
    statement_date = fields.Date(
        string='Fecha de corte',
        required=True,
        default=fields.Date.context_today,
        readonly=True,
    )
    show_draft_payments = fields.Boolean(
        string='Mostrar pagos pendientes de confirmación',
        default=True,
    )
    show_bank_accounts = fields.Boolean(
        string='Mostrar cuentas bancarias de la compañía',
        default=True,
    )

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        if (
            'partner_id' in field_names
            and self.env.context.get('active_model') == 'res.partner'
            and self.env.context.get('active_id')
        ):
            partner = self.env['res.partner'].browse(
                self.env.context['active_id']
            ).exists()
            if partner and partner.customer_rank > 0:
                values['partner_id'] = partner.id
        return values

    @api.constrains('company_id')
    def _check_company_access(self):
        for wizard in self:
            if wizard.company_id not in wizard.env.companies:
                raise ValidationError(_(
                    'La compañía seleccionada no está habilitada para su usuario.'
                ))

    @api.constrains('statement_date')
    def _check_statement_date(self):
        for wizard in self:
            if wizard.statement_date != fields.Date.context_today(wizard):
                raise ValidationError(_(
                    'Esta versión del estado de cuenta muestra saldos abiertos '
                    'actuales; la fecha de corte debe ser la fecha de hoy.'
                ))

    def _report_context(self):
        self.ensure_one()
        return {
            'allowed_company_ids': [self.company_id.id],
            'company_id': self.company_id.id,
            'force_company': self.company_id.id,
        }

    @staticmethod
    def _signed_amount(move, amount):
        sign = -1.0 if move.move_type == 'out_refund' else 1.0
        return sign * abs(amount or 0.0)

    def _get_open_moves(self):
        self.ensure_one()
        move_model = self.env['account.move']
        moves = move_model.search([
            ('partner_id', '=', self.partner_id.id),
            ('company_id', '=', self.company_id.id),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
            ('invoice_date', '<=', self.statement_date),
        ])
        if 'state_tributacion' in move_model._fields:
            moves = moves.filtered(
                lambda move: (move.state_tributacion or '').strip().lower()
                != 'rechazado'
            )
        return moves.filtered(
            lambda move: not move.currency_id.is_zero(move.amount_residual)
        )

    def _status_for_move(self, move):
        if move.move_type == 'out_refund':
            return {
                'key': 'credit',
                'label': _('Crédito disponible'),
                'days_overdue': 0,
            }

        due_date = move.invoice_date_due or move.invoice_date
        delta = (due_date - self.statement_date).days if due_date else 0
        if delta > 0:
            return {
                'key': 'upcoming',
                'label': _('Por vencer · %s días') % delta,
                'days_overdue': 0,
            }
        if delta == 0:
            return {
                'key': 'today',
                'label': _('Vence hoy'),
                'days_overdue': 0,
            }
        days_overdue = abs(delta)
        return {
            'key': 'overdue',
            'label': _('Vencida · %s días') % days_overdue,
            'days_overdue': days_overdue,
        }

    @staticmethod
    def _aging_key(days_overdue):
        if days_overdue <= 0:
            return 'not_due'
        if days_overdue <= 30:
            return '1_30'
        if days_overdue <= 60:
            return '31_60'
        if days_overdue <= 90:
            return '61_90'
        return '91_plus'

    def _prepare_currency_groups(self, moves):
        groups = {}
        for move in moves:
            currency = move.currency_id
            if currency.id not in groups:
                groups[currency.id] = {
                    'currency': currency,
                    'rows': [],
                    'balance': 0.0,
                    'overdue': 0.0,
                    'not_due': 0.0,
                    'credit_available': 0.0,
                    'aging': {
                        'not_due': 0.0,
                        '1_30': 0.0,
                        '31_60': 0.0,
                        '61_90': 0.0,
                        '91_plus': 0.0,
                    },
                }

            group = groups[currency.id]
            original = self._signed_amount(move, move.amount_total)
            balance = self._signed_amount(move, move.amount_residual)
            applied = self._signed_amount(
                move,
                max(abs(move.amount_total) - abs(move.amount_residual), 0.0),
            )
            status = self._status_for_move(move)

            group['balance'] += balance
            if move.move_type == 'out_refund':
                group['credit_available'] += abs(balance)
            else:
                aging_key = self._aging_key(status['days_overdue'])
                group['aging'][aging_key] += balance
                if aging_key == 'not_due':
                    group['not_due'] += balance
                else:
                    group['overdue'] += balance

            group['rows'].append({
                'document': move.name or move.ref or '',
                'document_type': (
                    _('Nota de crédito')
                    if move.move_type == 'out_refund'
                    else _('Factura')
                ),
                'invoice_date': move.invoice_date,
                'date_due': move.invoice_date_due or move.invoice_date,
                'currency': currency,
                'original': original,
                'applied': applied,
                'balance': balance,
                'status_key': status['key'],
                'status_label': status['label'],
            })

        for group in groups.values():
            group['rows'].sort(key=lambda row: (
                row['date_due'] or date.max,
                row['invoice_date'] or date.max,
                row['document'],
            ))

        company_currency = self.company_id.currency_id
        return sorted(
            groups.values(),
            key=lambda group: (
                group['currency'] != company_currency,
                group['currency'].name,
            ),
        )

    def _prepare_draft_payment_groups(self):
        self.ensure_one()
        if not self.show_draft_payments:
            return []

        payments = self.env['account.payment'].search([
            ('partner_id', '=', self.partner_id.id),
            ('company_id', '=', self.company_id.id),
            ('payment_type', '=', 'inbound'),
            ('state', '=', 'draft'),
            ('date', '<=', self.statement_date),
        ])
        totals = defaultdict(float)
        currencies = {}
        for payment in payments:
            currencies[payment.currency_id.id] = payment.currency_id
            totals[payment.currency_id.id] += payment.amount

        company_currency = self.company_id.currency_id
        return sorted(
            (
                {'currency': currencies[currency_id], 'amount': amount}
                for currency_id, amount in totals.items()
            ),
            key=lambda group: (
                group['currency'] != company_currency,
                group['currency'].name,
            ),
        )

    def _prepare_bank_accounts(self):
        self.ensure_one()
        if not self.show_bank_accounts:
            return []
        accounts = self.company_id.partner_id.bank_ids.filtered(
            lambda account: account.active
            and (not account.company_id or account.company_id == self.company_id)
        )
        return [
            {
                'bank_name': account.bank_id.name or '',
                'acc_number': account.acc_number or '',
                'currency_name': account.currency_id.name or '',
            }
            for account in accounts.sorted(
                key=lambda account: (
                    account.currency_id.name or '',
                    account.bank_id.name or '',
                    account.acc_number or '',
                )
            )[:4]
        ]

    def _prepare_statement_data(self):
        self.ensure_one()
        context = self._report_context()
        wizard = self.with_context(**context).with_company(self.company_id)
        moves = wizard._get_open_moves()
        if not moves:
            raise UserError(_(
                'El cliente seleccionado no tiene facturas ni notas de crédito '
                'abiertas en la compañía %s.'
            ) % self.company_id.display_name)

        partner = wizard.partner_id
        company_partner = wizard.company_id.partner_id
        return {
            'statement_date': wizard.statement_date,
            'company': wizard.company_id,
            'company_address': company_partner._display_address(
                without_company=True
            ),
            'partner': partner,
            'partner_address': partner._display_address(without_company=True),
            'commercial_name': partner.commercial_name or '',
            'customer_code': partner.unique_id or '',
            'payment_term': partner.property_payment_term_id.display_name or '',
            'currency_groups': wizard._prepare_currency_groups(moves),
            'document_count': len(moves),
            'draft_payment_groups': wizard._prepare_draft_payment_groups(),
            'bank_accounts': wizard._prepare_bank_accounts(),
        }

    def _report_action(self, xml_id):
        self.ensure_one()
        context = self._report_context()
        return self.env.ref(xml_id).with_context(**context).report_action(self)

    def action_preview_html(self):
        return self._report_action(
            'sng_customer_statement_client.'
            'action_report_customer_statement_client_html'
        )

    def action_print_pdf(self):
        return self._report_action(
            'sng_customer_statement_client.'
            'action_report_customer_statement_client_pdf'
        )
