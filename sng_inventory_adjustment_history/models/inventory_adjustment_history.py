# -*- coding: utf-8 -*-

import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class SngInventoryAdjustmentHistory(models.Model):
    _name = "sng.inventory.adjustment.history"
    _description = "Historial de Ajustes de Inventario"
    _order = "adjustment_date desc, id desc"
    _rec_name = "product_id"
    _check_company_auto = True

    adjustment_date = fields.Datetime(
        string="Fecha del ajuste",
        required=True,
        readonly=True,
        index=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Producto",
        required=True,
        readonly=True,
        check_company=True,
        index=True,
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Ubicación",
        required=True,
        readonly=True,
        check_company=True,
        index=True,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Almacén",
        required=True,
        readonly=True,
        check_company=True,
        index=True,
    )
    warehouse_group_ids = fields.Many2many(
        "sng.warehouse.group",
        "sng_inventory_adjustment_history_group_rel",
        "history_id",
        "group_id",
        string="Grupos de almacenes",
        required=True,
        readonly=True,
    )
    quant_id = fields.Many2one(
        "stock.quant",
        string="Cuanto de origen",
        readonly=True,
        ondelete="set null",
    )
    move_ids = fields.One2many(
        "stock.move",
        "sng_inventory_adjustment_history_id",
        string="Movimientos de inventario",
        readonly=True,
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lote/Número de serie",
        readonly=True,
        check_company=True,
        index=True,
    )
    package_id = fields.Many2one(
        "stock.quant.package",
        string="Paquete",
        readonly=True,
    )
    owner_id = fields.Many2one(
        "res.partner",
        string="Propietario",
        readonly=True,
    )
    uom_id = fields.Many2one(
        "uom.uom",
        string="Unidad de medida",
        required=True,
        readonly=True,
    )
    previous_quantity = fields.Float(
        string="Cantidad anterior",
        required=True,
        readonly=True,
        digits="Product Unit of Measure",
    )
    adjusted_quantity = fields.Float(
        string="Cantidad ajustada",
        required=True,
        readonly=True,
        digits="Product Unit of Measure",
    )
    new_quantity = fields.Float(
        string="Nueva cantidad",
        required=True,
        readonly=True,
        digits="Product Unit of Measure",
    )
    adjusted_by_id = fields.Many2one(
        "res.users",
        string="Ajustado por",
        required=True,
        readonly=True,
        index=True,
    )
    counted_by_id = fields.Many2one(
        "res.users",
        string="Contado por",
        readonly=True,
        help="Usuario asignado al conteo antes de aplicar el ajuste.",
    )
    unit_cost = fields.Monetary(
        string="Costo unitario",
        required=True,
        readonly=True,
        currency_field="currency_id",
        groups="custom_ui_security.group_view_product_cost",
    )
    adjustment_cost = fields.Monetary(
        string="Costo del ajuste",
        required=True,
        readonly=True,
        currency_field="currency_id",
        groups="custom_ui_security.group_view_product_cost",
        help="Impacto de valoración con signo: positivo para entradas y negativo para salidas.",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        related="company_id.currency_id",
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        readonly=True,
        index=True,
    )

    def _sng_send_adjustment_notifications(self):
        """Envía un correo resumen por cada grupo de almacenes con correos
        de alerta configurados, cubriendo los ajustes de este lote."""
        if not self:
            return
        mail_model = self.env["mail.mail"].sudo()
        for group in self.warehouse_group_ids.filtered("adjustment_notify_emails"):
            histories = self.filtered(lambda h: group in h.warehouse_group_ids)
            if not histories:
                continue
            try:
                adjustment_date = fields.Datetime.context_timestamp(
                    self, max(histories.mapped("adjustment_date"))
                )
                body = self.env["ir.qweb"]._render(
                    "sng_inventory_adjustment_history.mail_adjustment_notification",
                    {
                        "group": group,
                        "histories": histories,
                        "currency": histories[0].currency_id,
                        "total_cost": sum(histories.mapped("adjustment_cost")),
                    },
                )
                mail_model.create(
                    {
                        "subject": _(
                            "Ajustes de inventario: %(group)s — %(date)s",
                            group=group.name,
                            date=adjustment_date.strftime("%d/%m/%Y %H:%M"),
                        ),
                        "email_to": group.adjustment_notify_emails,
                        "email_from": self.env.company.email_formatted
                        or self.env.user.email_formatted,
                        "body_html": body,
                        "auto_delete": True,
                    }
                )
            except Exception:
                _logger.exception(
                    "No se pudo generar la alerta de ajuste de inventario "
                    "para el grupo %s",
                    group.name,
                )

