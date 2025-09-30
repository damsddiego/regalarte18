from odoo import api, fields, models

class ResPartner(models.Model):
    _inherit = "res.partner"

    delivery_type_id = fields.Many2one(
        "res.partner.delivery.type",
        string="Tipo de entrega",
        help="Selecciona el tipo de entrega por defecto para este contacto.",
        # base domain (refinado por onchange abajo)
        domain="[('active','=',True), '|', ('company_id','=', False), ('company_id','=', company_id)]",
    )

    @api.onchange("company_id")
    def _onchange_company_id_set_domain_delivery_type(self):
        """
        - Si el contacto tiene compañía: mostrar globales + su compañía.
        - Si NO tiene compañía: mostrar globales + compañías permitidas del usuario.
        """
        if self.company_id:
            domain = ['|', ('company_id', '=', False), ('company_id', '=', self.company_id.id)]
        else:
            allowed_ids = self.env.context.get('allowed_company_ids') or self.env.user.company_ids.ids
            domain = ['|', ('company_id', '=', False), ('company_id', 'in', allowed_ids)]
        return {'domain': {'delivery_type_id': domain}}
