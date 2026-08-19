# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    stock_notification_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="res_company_stock_notification_user_rel",
        column1="company_id",
        column2="user_id",
        string="Usuarios a notificar por falta de stock",
        help="Usuarios que recibirán notificación por correo y chat cuando una entrega no pueda validarse por falta de stock.",
    )
