from odoo import api, models
import logging

_logger = logging.getLogger(__name__)


class SngStockCustomerReport(models.AbstractModel):
    _name = "report.sng_stock_by_locations_report.report_stock_customer"
    _description = "Report Stock By Customer Location"

    @api.model
    def _get_report_values(self, docids, data=None):
        """Get report values for PDF rendering."""
        query_result = self.query_data(
            data['partner_ids'],
            data['companies'],
            data.get('date_from'),
            data.get('date_to')
        )

        # Calculate totals
        total_qty = sum(record.get('total_qty', 0) for record in query_result)
        total_value = sum(record.get('total_value', 0) for record in query_result)

        return {
            'doc_ids': docids,
            'doc_model': 'sng.stock.customer.report',
            'data': data,
            'records': query_result,
            'total_qty': total_qty,
            'total_value': total_value,
        }

    def query_data(self, partner_ids, company_ids, date_from=None, date_to=None):
        """Fetch customer stock data from database."""
        query = """
            SELECT
                rp.id as partner_id,
                rp.ref as unique_id,
                rp.name as partner_name,
                sl.complete_name as location_name,
                sl.id as location_id,
                SUM(sq.quantity) as total_qty,
                SUM(sq.quantity * pt.list_price) as total_value
            FROM
                stock_quant sq
            INNER JOIN
                stock_location sl ON sq.location_id = sl.id
            INNER JOIN
                res_partner rp ON sl.partner_id = rp.id
            INNER JOIN
                product_product pp ON sq.product_id = pp.id
            INNER JOIN
                product_template pt ON pp.product_tmpl_id = pt.id
            WHERE
                sl.usage = 'customer'
                AND rp.customer_rank > 0
                AND sq.quantity > 0
        """

        # Add filters
        params = {}

        if partner_ids:
            query += " AND rp.id IN %(partner_ids)s"
            params['partner_ids'] = tuple(partner_ids) if isinstance(partner_ids, (list, tuple)) else (partner_ids,)

        if company_ids:
            query += " AND sl.company_id IN %(company_ids)s"
            params['company_ids'] = tuple(company_ids) if isinstance(company_ids, (list, tuple)) else (company_ids,)

        # Note: Date filtering on stock_quant is tricky because it shows current state
        # If you need historical data, you'd need to query stock_move instead
        # For now, we're showing current stock as of today

        query += """
            GROUP BY
                rp.id, rp.ref, rp.name, sl.complete_name, sl.id
            HAVING
                SUM(sq.quantity) > 0
            ORDER BY
                rp.name, sl.complete_name
        """

        _logger.info("Executing query with params: %s", params)
        self.env.cr.execute(query, params)
        result = self.env.cr.dictfetchall()
        _logger.info("Query returned %d records", len(result))

        return result
