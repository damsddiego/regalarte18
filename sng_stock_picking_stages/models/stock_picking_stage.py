from odoo import fields, models


class StockPickingStage(models.Model):
    _name = 'stock.picking.stage'
    _description = 'Stock Picking Stage'
    _order = 'sequence, id'

    name = fields.Char(string="Name", required=True, translate=True)
    sequence = fields.Integer(string="Sequence", default=10)
    fold = fields.Boolean(string="Folded in Kanban")
    show_in_kanban = fields.Boolean(string="Show in Kanban", default=True)
    picking_type_code = fields.Selection(
        selection=[
            ('incoming', 'Receipt'),
            ('outgoing', 'Delivery'),
            ('internal', 'Internal Transfer'),
        ],
        string="Operation Type",
        help="Limit this stage to a specific operation type. "
             "Leave empty to show in all operation types.",
    )
