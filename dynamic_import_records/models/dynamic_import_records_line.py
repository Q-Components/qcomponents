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
                           'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', 'AA', 'AB', 'AC', 'AD', 'AE', 'AF', 'AG', 'AH', 'AI',
                           'AJ', 'AK', 'AL', 'AM', 'AN', 'AO', 'AP', 'AQ', 'AR', 'AS', 'AT', 'AU', 'AV', 'AW', 'AX',
                           'AY', 'AZ', 'BA', 'BB', 'BC', 'BD', 'BE', 'BF', 'BG', 'BH', 'BI', 'BJ', 'BK', 'BL', 'BM',
                           'BN', 'BO', 'BP', 'BQ', 'BR', 'BS', 'BT', 'BU', 'BV', 'BW', 'BX', 'BY', 'BZ', 'CA', 'CB',
                           'CC', 'CD', 'CE', 'CF', 'CG', 'CH', 'CI', 'CJ', 'CK', 'CL', 'CM', 'CN', 'CO', 'CP', 'CQ',
                           'CR', 'CS', 'CT', 'CU', 'CV', 'CW', ]:
                raise ValidationError(
                    "You need to enter CSV file column name from A-CW, we have handled upto 100 columns.")
            self.file_data = val.upper()

    @api.onchange('mapping_model_field_selection_id')
    def _set_relational_model_name(self):
        for rec in self:
            model_name = rec.mapping_model_field_selection_id.relation
            if rec.mapping_model_field_selection_id.ttype == 'many2one':
                rec.field_to_store_m2o_model_name = model_name
            if rec.mapping_model_field_selection_id.ttype == 'many2many':
                rec.field_to_store_m2m_model_name = model_name
            if rec.mapping_model_field_selection_id.ttype == 'one2many':
                rec.field_to_store_o2m_model_name = model_name

    dynamic_mapping_record_id = fields.Many2one(comodel_name='dynamic.import.records')
    file_data = fields.Char(string="File Data", help="Set Column Alphabet (From A-CW, we have handled upto 100 columns), from this column value fetch.")
    mapping_model_field_selection_id = fields.Many2one(comodel_name='ir.model.fields',
                                                       string="Selected Model Fields")
    visible_search_field_for_m2o = fields.Boolean(default=False)
    field_of_m2o_field = fields.Many2one(comodel_name='ir.model.fields', string="Field to search for M2O")
    visible_search_field_for_m2m = fields.Boolean(default=False)
    field_of_m2m_field = fields.Many2one(comodel_name='ir.model.fields', string="Field to search for M2M")
    visible_selection_field_for_o2m = fields.Boolean(default=False)
    field_to_store_m2o_model_name = fields.Char('M2O Model name')
    field_to_store_m2m_model_name = fields.Char('M2M Model name')
    field_to_store_o2m_model_name = fields.Char('O2M Model name')
    sequence = fields.Integer(help='Used to order Companies in the company switcher', default=10)
    sub_dynamic_mapping_record_id = fields.Many2one(comodel_name='dynamic.import.records', string='Sub Table')

    @api.onchange('mapping_model_field_selection_id')
    def _onchange_mapping_model_from(self):
        res = {'domain': {'mapping_model_field_selection_id': [], 'field_of_m2o_field': [], 'field_of_m2m_field': []}}
        if self.dynamic_mapping_record_id.model_id:
            res['domain']['mapping_model_field_selection_id'] = [
                ('model_id', '=', self.dynamic_mapping_record_id.model_id.name)]
            model_name = self.mapping_model_field_selection_id.relation
            if self.mapping_model_field_selection_id.ttype == 'many2one':
                self.visible_selection_field_for_o2m = False
                self.field_to_store_o2m_model_name = ''
                self.visible_search_field_for_m2o = True
                self.field_to_store_m2o_model_name = model_name
                res['domain']['field_of_m2o_field'] = [('model_id', '=', model_name)]
            elif self.mapping_model_field_selection_id.ttype == 'many2many':
                self.visible_selection_field_for_o2m = False
                self.field_to_store_o2m_model_name = ''
                self.visible_search_field_for_m2m = True
                self.field_to_store_m2m_model_name = model_name
                res['domain']['field_of_m2m_field'] = [('model_id', '=', model_name)]
            elif self.mapping_model_field_selection_id.ttype == 'one2many':
                self.visible_search_field_for_m2o = False
                self.visible_search_field_for_m2m = False
                self.field_of_m2o_field = False
                self.field_of_m2m_field = False
                self.field_to_store_m2o_model_name = ''
                self.field_to_store_m2m_model_name = ''
                self.visible_selection_field_for_o2m = True
                self.field_to_store_o2m_model_name = model_name
            else:
                self.visible_search_field_for_m2o = False
                self.visible_search_field_for_m2m = False
                self.visible_selection_field_for_o2m = False
                self.field_of_m2o_field = False
                self.field_of_m2m_field = False
        else:
            raise ValidationError("Please select the model first.")
        return res
