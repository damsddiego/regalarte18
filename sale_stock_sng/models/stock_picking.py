from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    @api.onchange('partner_id')
    def _onchange_partner_sale_locations(self):
        """
        Al seleccionar el contacto en el picking:
        - Solo aplica si el tipo de picking es transferencia entre bodegas.
        - La bodega de origen (`location_id`) se toma de la bodega del vendedor
          (res.users -> res.partner -> sale_location_id).
        - La bodega de destino (`location_dest_id`) se toma del contacto seleccionado
          (partner_id.sale_location_id).
        """
        for picking in self:

            if picking.picking_type_id.code != 'internal':
                continue

            if not picking.partner_id:
                continue

            user_sale_location = None
            if picking.partner_id.user_id:
                user_sale_location = picking.partner_id.user_id.partner_id.sale_location_id

            partner_sale_location = picking.partner_id.sale_location_id

            if user_sale_location:
                picking.location_id = user_sale_location

            if partner_sale_location:
                picking.location_dest_id = partner_sale_location