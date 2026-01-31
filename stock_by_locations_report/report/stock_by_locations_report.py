from odoo import api, models
from odoo.tools import groupby
import logging
_logger = logging.getLogger(__name__)

class StockLocationReport(models.AbstractModel):
    _name = "report.stock_by_locations_report.report_stock_locations"
    _description = "Report Stock By Location"

    @api.model
    def _get_report_values(self, docids, data=None):
        """To get the report values based on the user conditions"""

        # _logger.info("Rendering QWeb template with data: %s", data)

        # Fetch query data
        query_result = self.query_data(data['report_on'], data['product_ids'], data['locations'], data['measures'])

        # Group data by product name (assuming 'product' is a string, not a dict)
        grouped_data = {}
        for product_id, group in groupby(query_result, key=lambda x: x['product']):
            grouped_data[product_id] = list(group)

        return {
            'grouped_data': grouped_data,
            'var': query_result
        }


    def query_data(self, report_on, product_ids, locations, measures):
        """To fetch values from database using query"""
        query = """
        SELECT 
            CONCAT(
                pt.name::jsonb ->> 'en_US',
                CASE
                    WHEN variant_data.variant_names IS NOT NULL THEN
                        CONCAT(' (', variant_data.variant_names, ')')
                    ELSE ''
                END
            ) AS product,
                sl.complete_name AS Location,
                sl.company_id,
                SUM(smov.on_hand_qty) AS on_hand_qty,
                SUM(smov.qty_free) AS qty_free,
                SUM(smov.qty_reserved) AS qty_reserved,
                SUM(smov.forecast_qty) AS forecast_qty,
                SUM(smov.qty_incoming) AS qty_incoming,
                SUM(smov.qty_outgoing) AS qty_outgoing
                FROM (
                    SELECT 
                        product_id,
                        location_id,
                        COALESCE(SUM(qty_on_hand), 0) AS on_hand_qty,
                        COALESCE(SUM(qty_on_hand), 0) -
                        COALESCE(SUM(qty_outgoing), 0) AS qty_free,
                        COALESCE(SUM(qty_outgoing), 0) AS qty_reserved,
                        COALESCE(SUM(qty_on_hand), 0) +
                        COALESCE(SUM(qty_incoming), 0) - 
                        COALESCE(SUM(qty_outgoing), 0) AS forecast_qty,
                        COALESCE(SUM(qty_incoming), 0) AS qty_incoming,
                        COALESCE(SUM(qty_outgoing), 0) AS qty_outgoing
                    FROM (
                        -- On-hand quantity
                        SELECT 
                            product_id,
                            location_id AS location_id,
                            SUM(quantity) AS qty_on_hand,
                            0 AS qty_incoming,
                            0 AS qty_outgoing
                        FROM stock_quant
                        WHERE location_id IN (SELECT id FROM stock_location WHERE usage = 'internal')
                        GROUP BY location_id, product_id

                        UNION ALL

                        -- Incoming quantity
                        SELECT 
                            product_id,
                            location_dest_id AS location_id,
                            0 AS qty_on_hand,
                            SUM(product_qty) AS qty_incoming,
                            0 AS qty_outgoing
                        FROM stock_move
                        WHERE state IN ('confirmed', 'assigned', 'partially_available')
                        AND location_dest_id IN (SELECT id FROM stock_location WHERE usage = 'internal')
                        AND location_id NOT IN (SELECT id FROM stock_location WHERE usage = 'internal')
                        GROUP BY location_dest_id, product_id

                        UNION ALL

                        -- Outgoing quantity
                        SELECT 
                            product_id,
                            location_id AS location_id,
                            0 AS qty_on_hand,
                            0 AS qty_incoming,
                            SUM(product_qty) AS qty_outgoing
                        FROM stock_move
                        WHERE state IN ('confirmed', 'assigned', 'partially_available')
                        AND location_id IN (SELECT id FROM stock_location WHERE usage = 'internal')
                        AND location_dest_id NOT IN (SELECT id FROM stock_location WHERE usage = 'internal')
                        GROUP BY location_id, product_id
                    ) AS stock_data
                    GROUP BY location_id, product_id
                ) AS smov
                LEFT JOIN 
                    product_product pp ON smov.product_id = pp.id
                LEFT JOIN
                    product_template pt ON pp.product_tmpl_id = pt.id
                LEFT JOIN 
                    stock_location sl ON smov.location_id = sl.id
                LEFT JOIN (
                    -- Subquery to aggregate variant names
                    SELECT 
                        pvc.product_product_id,
                        STRING_AGG(pav.name::jsonb ->> 'en_US', ', ' ORDER BY pav.name::jsonb ->> 'en_US') AS variant_names
                    FROM 
                        product_variant_combination pvc
                    LEFT JOIN 
                        product_template_attribute_value ptav ON pvc.product_template_attribute_value_id = ptav.id
                    LEFT JOIN 
                        product_attribute_value pav ON ptav.product_attribute_value_id = pav.id
                    GROUP BY pvc.product_product_id
                ) AS variant_data ON pp.id = variant_data.product_product_id
            WHERE sl.usage = 'internal' 
            AND pt.type = 'consu' AND pt.is_storable
        """
        # Add filtering for product_id if given
        if product_ids:
            query += " AND pp.id IN %(product_ids)s"
        
        # Add filtering for locations if provided
        if locations:
            query += " AND (sl.id IN %(locations)s OR sl.id IS NULL)"

        query += " GROUP BY sl.company_id, sl.complete_name, pt.name, variant_data.variant_names;"

        # Prepare query parameters
        # query_params = {'product_ids': tuple(product_ids), 'locations': tuple(locations)}

        query_params = {
            'product_ids': tuple(product_ids) if isinstance(product_ids, (list, tuple)) else (product_ids,),
            'locations': tuple(locations) if isinstance(locations, (list, tuple)) else (locations,)
        }
       
        # Execute the query with the parameters
        self.env.cr.execute(query, query_params)
        return self.env.cr.dictfetchall()
