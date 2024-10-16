from odoo import models, fields, api
from odoo.exceptions import ValidationError


class DynamicImportRecords(models.Model):
    _name = 'dynamic.import.records'
    _description = "Dynamic Import Records"
    # _rec_name = "model_id"
    _order = 'sequence'

    name = fields.Char(string='Configuration Name')
    model_id = fields.Many2one(comodel_name='ir.model', string="Select Model in which you want to import records")
    search_record_from_this_value = fields.Char(string="Search record from this value",
                                                help="Set Column Alphabet (From A-Z), from this value check existing record available or not.")
    line_ids = fields.One2many(comodel_name='dynamic.import.records.line', inverse_name='dynamic_mapping_record_id')
    sequence = fields.Integer(help='Used to order Companies in the company switcher', default=10)
    main_table = fields.Boolean(string="Main Table", default=False)

    # _sql_constraints = [('model_id_uniq', 'unique(model_id)',
    #                      'Configuration record must be unique, you can create only one configuration per model.'), ]

    @api.onchange('search_record_from_this_value')
    def set_caps(self):
        if self.search_record_from_this_value:
            val = str(self.search_record_from_this_value).upper()
            if not val in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R',
                           'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', ]:
                raise ValidationError("You need to enter CSV file column name from A-Z.")
            self.search_record_from_this_value = val.upper()
