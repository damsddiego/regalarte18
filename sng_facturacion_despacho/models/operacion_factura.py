from odoo import fields, models


class OperacionFacturaDespacho(models.Model):
    _name = "sng.facturacion.despacho.operacion"
    _description = "Operación de facturación desde Despacho"

    orden_id = fields.Many2one("sale.order", required=True, ondelete="cascade")
    factura_id = fields.Many2one("account.move", ondelete="set null")
    solicitud = fields.Char(required=True)
    usuario_id = fields.Many2one("res.users", required=True, ondelete="restrict")
    contabilizada = fields.Boolean()

    _sql_constraints = [
        ("orden_unica", "unique(orden_id)", "Ya existe una operación para esta orden."),
    ]
