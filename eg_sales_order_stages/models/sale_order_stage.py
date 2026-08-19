from odoo import models, fields

class SaleOrderStage(models.Model):
    _name = 'sale.order.stage'
    _description = 'Sales Order Stage'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(string="Folded in Kanban")
    show_in_kanban = fields.Boolean(string="Show in Kanban", default=True)
