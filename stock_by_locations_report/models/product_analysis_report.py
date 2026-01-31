from odoo import fields, models, tools, api


class ProductAnalysisReport(models.Model):
    _name = 'product.analysis.report'
    _description = "Product Analysis Report"
    _auto = False

    product_tmpl_id = fields.Many2one('product.template', string="Product", help='Name of the product', readonly=True)
    product_id = fields.Many2one('product.product', string="Product Variant", help='Name of the product variant', readonly=True)
    categ_id = fields.Many2one('product.category', string="Product Category", help='Name of the product category', readonly=True)
    location_id = fields.Many2one('stock.location', string='Location', help='Choose the location', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', help='Company', readonly=True)
    on_hand_qty = fields.Float(string='On Hand', help='On hand quantity of the product', readonly=True)
    qty_incoming = fields.Float(string='Incoming', help='Incoming quantity of the product', readonly=True)
    qty_outgoing = fields.Float(string='Outgoing', help='Outgoing quantity of the product', readonly=True)
    forecast_qty = fields.Float(string='Forecast', help='Forecasted quantity of the product', readonly=True)
    qty_free = fields.Float(string='Free To Use', help='Free to use quantity of the product', readonly=True)
    qty_reserved = fields.Float(string='Reserved', help='Reserved quantity of the product', readonly=True)

    @api.model
    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)
        self._cr.execute('''CREATE OR REPLACE VIEW %s AS (
                SELECT 
					ROW_NUMBER() OVER () AS id,
					pp.id AS product_id,
					pt.id AS product_tmpl_id, 
					pt.categ_id AS categ_id,
					sl.id AS location_id,
					sl.company_id AS company_id,
					smov.on_hand_qty AS on_hand_qty,
					smov.qty_free AS qty_free,
					smov.qty_reserved AS qty_reserved,
					smov.forecast_qty AS forecast_qty,
					smov.qty_incoming AS qty_incoming,
					smov.qty_outgoing AS qty_outgoing
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
				WHERE sl.usage = 'internal' 
				AND pt.type = 'consu' AND pt.is_storable
                         )'''% (self._table,))
