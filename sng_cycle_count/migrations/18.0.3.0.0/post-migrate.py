# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    if version:
        env = api.Environment(cr, SUPERUSER_ID, {})
        env["sng.cycle.count"]._migrate_cycle_controls()
