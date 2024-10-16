from odoo import models, fields, api
from odoo.exceptions import ValidationError


class DynamicImportRecordsLine(models.Model):
    _name = 'dynamic.import.records.line'
    _description = "Dynamic Import Records Line"
    _order = 'sequence'

    @api.onchange('file_data')
    def check_entered_value(self):
        if self.file_data:
            val = str(self.file_data).upper()
            if not val in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R',
                           'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', ]:
                raise ValidationError("You need to enter CSV file column name from A-Z.")
            self.file_data = val.upper()

    @api.onchange('dynamic_mapping_record_id.model_id')
    def _set_main_model_name(self):
        for rec in self:
            model_name = rec.dynamic_mapping_record_id.model_id.model
            rec.field_to_store_main_model_name = model_name

    @api.onchange('mapping_model_field_selection_id')
    def _set_relational_model_name(self):
        for rec in self:
            model_name = rec.mapping_model_field_selection_id.relation
            if rec.mapping_model_field_selection_id.ttype == 'many2one':
                rec.field_to_store_m2o_model_name = model_name
            if rec.mapping_model_field_selection_id.ttype == 'one2many':
                rec.field_to_store_o2m_model_name = model_name

    dynamic_mapping_record_id = fields.Many2one(comodel_name='dynamic.import.records')
    file_data = fields.Char(string="File Data")
    mapping_model_field_selection_id = fields.Many2one(comodel_name='ir.model.fields',
                                                       string="Selected Model Fields")
    visible_search_field_for_m2o = fields.Boolean(default=False)
    field_of_m2o_field = fields.Many2one(comodel_name='ir.model.fields', string="Field to search for M2O")
    visible_selection_field_for_o2m = fields.Boolean(default=False)
    field_to_store_main_model_name = fields.Char('Main Model name', compute='_set_main_model_name')
    field_to_store_m2o_model_name = fields.Char('M2O Model name')
    field_to_store_o2m_model_name = fields.Char('O2M Model name')
    sequence = fields.Integer(help='Used to order Companies in the company switcher', default=10)
    sub_dynamic_mapping_record_id = fields.Many2one(comodel_name='dynamic.import.records', string='Sub Table')

    @api.onchange('mapping_model_field_selection_id')
    def _onchange_mapping_model_from(self):
        res = {'domain': {'mapping_model_field_selection_id': [], 'field_of_m2o_field': []}}
        if self.dynamic_mapping_record_id.model_id:
            res['domain']['mapping_model_field_selection_id'] = [
                ('model_id', '=', self.dynamic_mapping_record_id.model_id.name)]
            model_name = self.mapping_model_field_selection_id.relation
            if self.mapping_model_field_selection_id.ttype == 'many2one':
                self.visible_selection_field_for_o2m = False
                self.field_to_store_o2m_model_name = ''
                self.visible_search_field_for_m2o = True
                self.field_to_store_m2o_model_name = model_name
                res['domain']['field_of_m2o_field'] = [
                    ('model_id', '=', model_name)]
            elif self.mapping_model_field_selection_id.ttype == 'one2many':
                self.visible_search_field_for_m2o = False
                self.field_of_m2o_field = False
                self.field_to_store_m2o_model_name = ''
                self.visible_selection_field_for_o2m = True
                self.field_to_store_o2m_model_name = model_name
            else:
                self.visible_search_field_for_m2o = False
                self.visible_selection_field_for_o2m = False
                self.field_of_m2o_field = False
        else:
            raise ValidationError("Please select the model first.")
        return res
