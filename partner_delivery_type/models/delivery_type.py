from odoo import api, fields, models

class ResPartnerDeliveryType(models.Model):
    _name = "res.partner.delivery.type"
    _description = "Tipo de entrega de Contacto"
    _order = "sequence, name"
    _check_company_auto = True

    name = fields.Char("Nombre", required=True, translate=True)
    code = fields.Char("Código", help="Identificador corto, p.ej. AJU, ENC, RUTA.")
    sequence = fields.Integer("Secuencia", default=10)
    active = fields.Boolean("Activo", default=True)
    note = fields.Text("Descripción")

    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        index=True,
        default=lambda self: self.env.company,
        help="Si se deja vacío, el tipo queda disponible para todas las compañías.",
    )

    _sql_constraints = [
        ("name_company_uniq", "unique(name, company_id)",
         "El nombre del Tipo de entrega debe ser único por compañía."),
    ]

    @api.onchange("name")
    def _onchange_name_set_code(self):
        if self.name and not self.code:
            self.code = (self.name or "").strip().lower().replace(" ", "_")[:16]
