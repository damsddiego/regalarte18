from odoo import fields, models, api


class ProductProduct(models.Model):
    _inherit = 'product.product'

    stock_by_locations = fields.One2many('product.analysis.report', 'product_id', compute="_compute_stock_by_locations", string="Stock by locations", readonly=True)


    def _compute_stock_by_locations(self):
        for product in self:
            product.stock_by_locations = self.env['product.analysis.report'].search([
                ('product_id', '=', product.id), ('company_id', 'in', self.env.companies.ids)
                ])
