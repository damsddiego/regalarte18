# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SngWarehouseGroup(models.Model):
    _name = "sng.warehouse.group"
    _description = "Grupo de Almacenes"
    _order = "sequence, name, id"

    name = fields.Char(string="Nombre", required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    warehouse_ids = fields.Many2many(
        "stock.warehouse",
        "sng_warehouse_group_warehouse_rel",
        "group_id",
        "warehouse_id",
        string="Almacenes",
        required=True,
    )
    notes = fields.Text(string="Notas")

    @api.model_create_multi
    def create(self, vals_list):
        groups = super().create(vals_list)
        groups._check_warehouse_ids()
        return groups

    @api.constrains("warehouse_ids")
    def _check_warehouse_ids(self):
        for group in self:
            if not group.warehouse_ids:
                raise ValidationError(_("El grupo debe contener al menos un almacén."))
