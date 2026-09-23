# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_is_zero


class StockQuant(models.Model):
    _inherit = "stock.quant"

    sng_adjustment_reason = fields.Text(string="Motivo del ajuste")
    sng_counted_by_ids = fields.Many2many(
        "res.users", "sng_quant_counter_rel", "quant_id", "user_id",
        string="Participantes del conteo manual", readonly=True, copy=False,
    )
    sng_last_counted_by_id = fields.Many2one("res.users", readonly=True, copy=False)

    def _sng_record_capture(self):
        for quant in self:
            super(StockQuant, quant.sudo()).write({
                "sng_counted_by_ids": [fields.Command.link(self.env.uid)],
                "sng_last_counted_by_id": self.env.uid,
            })

    def _sng_check_independent_capture(self):
        for quant in self:
            if not quant.sng_counted_by_ids:
                raise UserError(_("Registre nuevamente la cantidad para identificar al capturador."))
            if self.env.user in quant.sng_counted_by_ids:
                raise AccessError(_("Quien contó o recontó no puede aplicar ese mismo ajuste."))

    def _sng_check_inventory_approval_access(self):
        if not self.env.su and not self.env.user.has_group(
            "sng_inventory_adjustment_history.group_inventory_adjustment_approver"
        ):
            raise AccessError(_(
                "Solo Gerencia autorizada puede aplicar ajustes de inventario. "
                "Registre el conteo y el motivo, y use Solicitar aprobación."
            ))

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any("inventory_diff_quantity" in vals for vals in vals_list):
            raise AccessError(_("La diferencia de inventario la calcula el servidor."))
        if not self.env.su and any({"sng_counted_by_ids", "sng_last_counted_by_id"}.intersection(v) for v in vals_list):
            raise AccessError(_("La identidad del capturador la registra el servidor."))
        # Check before native stock.quant.create() escalates to sudo in inventory mode.
        if any({"inventory_quantity_auto_apply", "quantity"}.intersection(vals) for vals in vals_list):
            self._sng_check_inventory_approval_access()
            if not self.env.su:
                raise UserError(_("Registre la cantidad contada y solicite aprobación a otro usuario."))
        if not self._is_inventory_mode():
            return super().create(vals_list)
        quants = self.browse()
        for vals in vals_list:
            if {"inventory_quantity", "inventory_quantity_auto_apply"}.intersection(vals):
                existing = self._gather(
                    self.env["product.product"].browse(vals.get("product_id")),
                    self.env["stock.location"].browse(vals.get("location_id")),
                    lot_id=self.env["stock.lot"].browse(vals.get("lot_id")),
                    package_id=self.env["stock.quant.package"].browse(vals.get("package_id")),
                    owner_id=self.env["res.partner"].browse(vals.get("owner_id")),
                    strict=True,
                )
                if not self.env.su:
                    existing._sng_check_no_pending_request()
            quant = super().create([dict(vals)])
            if "inventory_quantity" in vals and not self.env.su:
                quant.with_env(self.env)._sng_record_capture()
            if "sng_adjustment_reason" in vals:
                quant.sng_adjustment_reason = vals["sng_adjustment_reason"]
            quants |= quant
        return quants

    def _sng_check_no_pending_request(self):
        if self.env["sng.inventory.adjustment.request"].sudo().search_count([
            ("quant_id", "in", self.ids), ("state", "=", "pending"),
        ]):
            raise UserError(_("Existe una solicitud por aprobar. Gerencia debe aprobarla o rechazarla."))

    def write(self, vals):
        if not self.env.su and "inventory_diff_quantity" in vals:
            raise AccessError(_("La diferencia de inventario la calcula el servidor."))
        if not self.env.su and {"sng_counted_by_ids", "sng_last_counted_by_id"}.intersection(vals):
            raise AccessError(_("La identidad del capturador la registra el servidor."))
        if {"inventory_quantity_auto_apply", "quantity"}.intersection(vals):
            self._sng_check_inventory_approval_access()
            if not self.env.su:
                raise UserError(_("Registre la cantidad contada y solicite aprobación a otro usuario."))
        if not self.env.su and {
            "inventory_quantity", "inventory_quantity_auto_apply", "inventory_diff_quantity",
            "inventory_quantity_set", "sng_adjustment_reason", "user_id",
        }.intersection(vals):
            self._sng_check_no_pending_request()
        result = super().write(vals)
        if "inventory_quantity" in vals and not self.env.su:
            self._sng_record_capture()
        return result

    @api.model
    def _get_inventory_fields_write(self):
        return super()._get_inventory_fields_write() + ["sng_adjustment_reason"]

    def action_apply_inventory(self):
        self._sng_check_inventory_approval_access()
        return super().action_apply_inventory()

    def action_apply_all(self):
        self._sng_check_inventory_approval_access()
        return super().action_apply_all()

    def action_clear_inventory_quantity(self):
        self.check_access("write")
        if not self.env.su:
            self._sng_check_no_pending_request()
        # Native clearing resets the computed difference explicitly. It is not
        # a new physical capture and must not register the approver as a counter.
        # Keep the participants until an adjustment has actually been applied.
        return super(StockQuant, self.sudo()).action_clear_inventory_quantity()

    def action_request_inventory_approval(self):
        self.check_access("write")
        if not self or any(not quant.inventory_quantity_set for quant in self):
            raise UserError(_("Registre el conteo físico antes de solicitar aprobación."))
        if any(quant.is_outdated for quant in self):
            raise UserError(_("Las existencias cambiaron. Revise y registre nuevamente el conteo."))
        requests = self.env["sng.inventory.adjustment.request"]._create_from_quants(self)
        requests.action_submit()
        return {
            "type": "ir.actions.act_window", "name": _("Solicitudes de ajuste"),
            "res_model": requests._name, "view_mode": "list,form",
            "domain": [("id", "in", requests.ids)],
        }

    def unlink(self):
        # Keep quants referenced by requests, including automatic cleanup of zero quants.
        referenced = self.env["sng.inventory.adjustment.request"].sudo().search([
            ("quant_id", "in", self.ids),
        ]).quant_id
        return super(StockQuant, self - referenced).unlink()

    def _sng_get_adjustment_unit_cost(self):
        self.ensure_one()
        product = self.product_id.with_company(self.company_id)
        if product.lot_valuated and self.lot_id:
            return self.lot_id.with_company(self.company_id).standard_price
        return product.standard_price

    def _sng_prepare_adjustment_history_vals(self, warehouse_groups):
        self.ensure_one()
        unit_cost = self._sng_get_adjustment_unit_cost()
        adjusted_quantity = self.inventory_quantity - self.quantity
        return {
            "adjustment_date": fields.Datetime.now(),
            "product_id": self.product_id.id,
            "location_id": self.location_id.id,
            "warehouse_id": self.location_id.warehouse_id.id,
            "warehouse_group_ids": [(6, 0, warehouse_groups.ids)],
            "quant_id": self.id,
            "lot_id": self.lot_id.id,
            "package_id": self.package_id.id,
            "owner_id": self.owner_id.id,
            "uom_id": self.product_uom_id.id,
            "previous_quantity": self.quantity,
            "adjusted_quantity": adjusted_quantity,
            "new_quantity": self.inventory_quantity,
            "adjusted_by_id": self.env.user.id,
            "counted_by_id": self.sng_last_counted_by_id.id or self.user_id.id,
            "unit_cost": unit_cost,
            "adjustment_cost": adjusted_quantity * unit_cost,
            "company_id": self.company_id.id or self.env.company.id,
            "request_id": self.env.context.get("sng_adjustment_request_id"),
        }

    def _apply_inventory(self):
        self._sng_check_inventory_approval_access()
        if not self.env.su:
            self._sng_check_independent_capture()
        if not self.env.su and self.env["sng.inventory.adjustment.request"].sudo().search_count([
            ("quant_id", "in", self.ids), ("state", "=", "pending"),
        ]):
            raise UserError(_("Aplique el ajuste desde la solicitud pendiente de aprobación."))
        grouped_quants = self.filtered("location_id.warehouse_id")
        groups_by_warehouse = {}
        if grouped_quants:
            groups = self.env["sng.warehouse.group"].search(
                [("warehouse_ids", "in", grouped_quants.location_id.warehouse_id.ids)]
            )
            for warehouse in grouped_quants.location_id.warehouse_id:
                groups_by_warehouse[warehouse.id] = groups.filtered(
                    lambda group, warehouse=warehouse: warehouse in group.warehouse_ids
                )

        history_model = self.env["sng.inventory.adjustment.history"].sudo()
        histories_by_quant = {}
        for quant in self:
            warehouse_groups = groups_by_warehouse.get(quant.location_id.warehouse_id.id)
            if not warehouse_groups:
                continue
            history = history_model.create(
                quant._sng_prepare_adjustment_history_vals(warehouse_groups)
            )
            histories_by_quant[quant.id] = history.id

        self = self.with_context(
            sng_inventory_adjustment_histories=histories_by_quant
        )
        result = super()._apply_inventory()

        histories = history_model.browse(list(histories_by_quant.values()))
        for history in histories:
            valuation_layers = history.move_ids.sudo().stock_valuation_layer_ids
            if not valuation_layers:
                continue
            valuation_quantity = sum(valuation_layers.mapped("quantity"))
            valuation_value = sum(valuation_layers.mapped("value"))
            unit_cost = history.unit_cost
            if not float_is_zero(
                valuation_quantity,
                precision_rounding=history.uom_id.rounding,
            ):
                unit_cost = abs(valuation_value / valuation_quantity)
            history.write(
                {
                    "unit_cost": unit_cost,
                    "adjustment_cost": valuation_value,
                }
            )
        histories._sng_send_adjustment_notifications()
        super(StockQuant, self.sudo()).write({
            "sng_counted_by_ids": [fields.Command.clear()], "sng_last_counted_by_id": False,
        })
        return result

    def _get_inventory_move_values(
        self,
        qty,
        location_id,
        location_dest_id,
        package_id=False,
        package_dest_id=False,
    ):
        values = super()._get_inventory_move_values(
            qty,
            location_id,
            location_dest_id,
            package_id=package_id,
            package_dest_id=package_dest_id,
        )
        history_id = self.env.context.get(
            "sng_inventory_adjustment_histories", {}
        ).get(self.id)
        if history_id:
            values["sng_inventory_adjustment_history_id"] = history_id
        if self.env.context.get("sng_adjustment_request_id"):
            values["sng_adjustment_request_id"] = self.env.context["sng_adjustment_request_id"]
        return values
