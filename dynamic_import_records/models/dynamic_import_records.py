from odoo import models, fields, api
from odoo.exceptions import ValidationError


class DynamicImportRecords(models.Model):
    _name = 'dynamic.import.records'
    _description = "Dynamic Import Records"
    _order = 'sequence'

    name = fields.Char(string='Configuration Name')
    model_id = fields.Many2one(comodel_name='ir.model', string="Select Model in which you want to import records")
    search_record_from_this_value = fields.Char(string="Search record from this value",
                                                help="Set Column Alphabet (From A-CW, we have handled upto 100 columns), from this value check existing record available or not.")
    line_ids = fields.One2many(comodel_name='dynamic.import.records.line', inverse_name='dynamic_mapping_record_id')
    sequence = fields.Integer(help='Used to order Companies in the company switcher', default=10)
    main_table = fields.Boolean(string="Main Table", default=False)
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Partner',
        default=lambda self: self.env.company.partner_id
    )
    default_value_dynamic_records = fields.Char(
        string="Default Value",
        help="Ability to set default values in EDI model mapping."
    )

    @api.depends('partner_id')
    def _compute_display_name(self):
        """ Display 'Dynamic Import Record name : Partner_id name' """
        for i in self:
            if i.partner_id:
                i.display_name = f"{i.name}: {i.partner_id.name}"
            else:
                i.display_name = f"{i.name}"

    @api.onchange('search_record_from_this_value')
    def set_caps(self):
        if self.search_record_from_this_value:
            val = str(self.search_record_from_this_value).upper()
            if not val in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R',
                           'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', 'AA', 'AB', 'AC', 'AD', 'AE', 'AF', 'AG', 'AH', 'AI',
                           'AJ', 'AK', 'AL', 'AM', 'AN', 'AO', 'AP', 'AQ', 'AR', 'AS', 'AT', 'AU', 'AV', 'AW', 'AX',
                           'AY', 'AZ', 'BA', 'BB', 'BC', 'BD', 'BE', 'BF', 'BG', 'BH', 'BI', 'BJ', 'BK', 'BL', 'BM',
                           'BN', 'BO', 'BP', 'BQ', 'BR', 'BS', 'BT', 'BU', 'BV', 'BW', 'BX', 'BY', 'BZ', 'CA', 'CB',
                           'CC', 'CD', 'CE', 'CF', 'CG', 'CH', 'CI', 'CJ', 'CK', 'CL', 'CM', 'CN', 'CO', 'CP', 'CQ',
                           'CR', 'CS', 'CT', 'CU', 'CV', 'CW', ]:
                raise ValidationError(
                    "You need to enter CSV file column name from A-CW, we have handled upto 100 columns.")
            self.search_record_from_this_value = val.upper()
