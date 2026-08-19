from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    stage_id = fields.Many2one(
        comodel_name='stock.picking.stage',
        string="Stage",
        tracking=True,
        store=True,
        copy=False,
        default=lambda self: self._default_stage_id(),
        group_expand='_read_group_stage_ids',
    )

    def _default_stage_id(self):
        picking_type_code = self.env.context.get('default_picking_type_code')
        domain = [('show_in_kanban', '=', True)]
        if picking_type_code:
            domain += [('picking_type_code', 'in', [picking_type_code, False])]
        return self.env['stock.picking.stage'].search(domain, order='sequence, id', limit=1)

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        return stages.search([('show_in_kanban', '=', True)], order=stages._order)
