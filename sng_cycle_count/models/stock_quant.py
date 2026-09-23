# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

from .cycle_count import SUPERVISOR_GROUP


class StockQuant(models.Model):
    _inherit = "stock.quant"

    sng_cycle_line_id = fields.Many2one("sng.cycle.count.line", readonly=True, copy=False,
                                       ondelete="set null", index=True, string="Línea cíclica")
    sng_cycle_id = fields.Many2one(related="sng_cycle_line_id.cycle_count_id", string="Sesión cíclica")
    sng_cycle_quantity = fields.Float(related="sng_cycle_line_id.counted_qty", string="Conteo cíclico")
    sng_cycle_difference = fields.Float(related="sng_cycle_line_id.difference_qty", string="Diferencia cíclica")
    sng_cycle_review = fields.Selection(related="sng_cycle_line_id.review_state", string="Revisión cíclica")
    sng_cycle_deadline = fields.Datetime(related="sng_cycle_line_id.deadline_at", store=True, string="Vence el")
    sng_cycle_pending = fields.Boolean(related="sng_cycle_line_id.unresolved", store=True)
    sng_cycle_overdue = fields.Boolean(related="sng_cycle_line_id.is_overdue", string="Cíclico vencido")
    sng_cycle_warning = fields.Boolean(related="sng_cycle_line_id.is_warning", string="Cíclico por vencer")

    def _cycle_lock(self):
        self.flush_recordset()
        if self:
            self.env.cr.execute("SELECT id FROM stock_quant WHERE id = ANY(%s) ORDER BY id FOR UPDATE", [sorted(self.ids)])
            self.invalidate_recordset()

    def _cycle_check_no_session(self):
        if any(self.sudo().mapped("sng_cycle_line_id")):
            raise UserError(_("Esta existencia pertenece a un conteo cíclico abierto. Resuélvalo desde la sesión."))

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            if any("sng_cycle_line_id" in vals for vals in vals_list):
                raise AccessError(_("El vínculo al conteo lo administra el servidor."))
            if not self._is_inventory_mode():
                raise AccessError(_("Registre productos desde el flujo autorizado de inventario."))
            if self._is_inventory_mode():
                for vals in vals_list:
                    existing = self._gather(
                        self.env["product.product"].browse(vals.get("product_id")),
                        self.env["stock.location"].browse(vals.get("location_id")),
                        lot_id=self.env["stock.lot"].browse(vals.get("lot_id")),
                        package_id=self.env["stock.quant.package"].browse(vals.get("package_id")),
                        owner_id=self.env["res.partner"].browse(vals.get("owner_id")), strict=True,
                    )
                    existing._cycle_lock()
                    existing._cycle_check_no_session()
                    if not existing and not self.env.user.has_group(SUPERVISOR_GROUP):
                        raise AccessError(_("El operador no puede agregar productos libres al inventario."))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            if "sng_cycle_line_id" in vals:
                raise AccessError(_("El vínculo al conteo lo administra el servidor."))
            if {"inventory_quantity", "inventory_quantity_auto_apply", "sng_adjustment_reason", "quantity"}.intersection(vals):
                self._cycle_lock()
            lines = self.sudo().sng_cycle_line_id.with_env(self.env)
            if lines and {"inventory_quantity_auto_apply", "quantity", "inventory_diff_quantity", "inventory_quantity_set",
                          "location_id", "lot_id", "package_id", "owner_id", "product_id", "user_id"}.intersection(vals):
                raise UserError(_("Use las acciones de la sesión para modificar el conteo cíclico."))
            if lines and {"inventory_quantity", "sng_adjustment_reason"}.intersection(vals):
                values = {}
                if "inventory_quantity" in vals:
                    values["counted_qty"] = vals["inventory_quantity"]
                if "sng_adjustment_reason" in vals:
                    values["notes"] = vals["sng_adjustment_reason"]
                lines.write(values)
                remaining = self - lines.quant_id
                if remaining:
                    remaining.write(vals)
                extra = {k: v for k, v in vals.items() if k not in ("inventory_quantity", "sng_adjustment_reason")}
                return super(StockQuant, self - remaining).write(extra) if extra else True
        return super().write(vals)

    def action_request_inventory_approval(self):
        self._cycle_check_no_session()
        return super().action_request_inventory_approval()

    def _apply_inventory(self):
        if not self.env.su:
            self._cycle_check_no_session()
        return super()._apply_inventory()

    def action_clear_inventory_quantity(self):
        if not self.env.su:
            self._cycle_check_no_session()
        return super().action_clear_inventory_quantity()

    def action_cycle_send_review(self):
        lines = self.sudo().sng_cycle_line_id.with_env(self.env)
        lines.action_send_for_review()
        return True

    def action_cycle_open_line(self):
        self.ensure_one()
        return self.sng_cycle_line_id.action_open_control()

    def action_set_inventory_quantity(self):
        if not self.env.su and not self.env.user.has_group(SUPERVISOR_GROUP):
            raise AccessError(_("El operador debe registrar el conteo físico, no copiar el teórico."))
        self._cycle_check_no_session()
        return super().action_set_inventory_quantity()

    def action_view_inventory(self):
        action = super().action_view_inventory()
        action["context"].update(search_default_cycle_pending=1, search_default_my_count=0)
        return action

    def unlink(self):
        """Odoo borra en bloque los quants en cero (``_unlink_zero_quants``) al
        abrir Disponible o tras movimientos. Las líneas de conteo cíclico apuntan
        al quant con ``ondelete=restrict`` para conservar el historial, lo que
        provocaba un error de FK en toda la pantalla de existencias. Los quants
        referenciados por un conteo se conservan (en cero) y se excluyen del borrado."""
        if not self:
            return super().unlink()
        referenced_ids = {
            group["quant_id"][0]
            for group in self.env["sng.cycle.count.line"]
            .sudo()
            .read_group([("quant_id", "in", self.ids)], ["quant_id"], ["quant_id"])
        }
        if not referenced_ids:
            return super().unlink()
        return super(StockQuant, self - self.browse(list(referenced_ids))).unlink()
