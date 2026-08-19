# -*- coding: utf-8 -*-
from odoo import fields, models


class MailingContact(models.Model):
    _inherit = "mailing.contact"

    partner_id = fields.Many2one(
        "res.partner",
        string="Cliente",
        index=True,
        ondelete="set null",
        help="Cliente del que se importó este contacto.",
    )
