# -*- coding: utf-8 -*-
from datetime import date, datetime

from odoo import api, models


class CustomerStatementClientReport(models.AbstractModel):
    _name = (
        'report.sng_customer_statement_client.'
        'report_customer_statement_client'
    )
    _table = 'report_sng_customer_stmt_client'
    _description = 'Reporte: Estado de Cuenta para Cliente'

    @staticmethod
    def _format_date(value):
        if not value:
            return ''
        if isinstance(value, datetime):
            value = value.date()
        if isinstance(value, date):
            return value.strftime('%d/%m/%Y')
        return str(value)

    @staticmethod
    def _format_long_date(value):
        if not value:
            return ''
        if isinstance(value, datetime):
            value = value.date()
        if not isinstance(value, date):
            return str(value)
        months = (
            'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
            'julio', 'agosto', 'septiembre', 'octubre', 'noviembre',
            'diciembre',
        )
        return f'{value.day} de {months[value.month - 1]} de {value.year}'

    @staticmethod
    def _format_money(value, currency):
        amount = float(value or 0.0)
        digits = currency.decimal_places
        number = f'{abs(amount):,.{digits}f}'
        number = number.replace(',', 'X').replace('.', ',').replace('X', '.')
        sign = '-' if amount < 0 else ''
        symbol = currency.symbol or currency.name
        if currency.position == 'after':
            return f'{sign}{number} {symbol}'
        return f'{sign}{symbol}{number}'

    @staticmethod
    def _format_currency_name(currency):
        labels = {
            'CRC': 'Colones',
            'USD': 'Dólares',
        }
        return labels.get(currency.name, currency.display_name)

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['sng.customer.statement.client.wizard'].browse(
            docids or []
        ).exists()
        wizard = docs[:1]
        statement = wizard._prepare_statement_data() if wizard else {}
        company = statement.get('company') or self.env.company
        return {
            'doc_ids': docs.ids,
            'doc_model': 'sng.customer.statement.client.wizard',
            'docs': docs,
            'data': statement,
            'company': company,
            'fmt_date': self._format_date,
            'fmt_long_date': self._format_long_date,
            'fmt_money': self._format_money,
            'fmt_currency_name': self._format_currency_name,
        }
