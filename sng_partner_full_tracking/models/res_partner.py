# -*- coding: utf-8 -*-
from odoo import models

# Campos técnicos de mail/activity que no deben aparecer en el tracking
_EXCLUDED_TRACKING_FIELDS = {
    # mail.thread
    'message_is_follower',
    'message_follower_ids',
    'message_partner_ids',
    'message_channel_ids',
    'message_ids',
    'message_needaction',
    'message_needaction_counter',
    'message_has_error',
    'message_has_error_counter',
    'message_attachment_count',
    'message_main_attachment_id',
    # mail.thread.blacklist
    'email_normalized',
    'is_blacklisted',
    'message_bounce',
    # mail.activity.mixin
    'activity_ids',
    'activity_state',
    'activity_user_id',
    'activity_type_id',
    'activity_type_icon',
    'activity_date_deadline',
    'my_activity_date_deadline',
    'activity_summary',
    'activity_exception_decoration',
    'activity_exception_icon',
}

_SUPPORTED_TRACKING_FIELD_TYPES = {
    'integer',
    'float',
    'char',
    'text',
    'datetime',
    'monetary',
    'date',
    'boolean',
    'selection',
    'many2one',
    'one2many',
    'many2many',
}


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _track_get_fields(self):
        """Devuelve los campos almacenados soportados como trackeables."""
        tracked = super()._track_get_fields()
        stored_fields = {
            name
            for name, field in self._fields.items()
            if field.store
            and name not in _EXCLUDED_TRACKING_FIELDS
            and field.type in _SUPPORTED_TRACKING_FIELD_TYPES
        }
        return tracked | stored_fields
