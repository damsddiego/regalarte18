from odoo import models, fields


class MeasureOption(models.Model):
    _name = 'measure.option'
    _description = 'Measure Option'

    name = fields.Char(string='Measure')
