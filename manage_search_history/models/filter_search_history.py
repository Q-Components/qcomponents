from odoo import models, fields,api

class FilterSearchHistory(models.Model):
    _name="filter.search.history"
    _description= "Odoo Backend Filter Search History"

    field_name = fields.Char('Field Name')
    shared_user_ids = fields.Many2many('res.users',string="Shared With")
    domain = fields.Text(default='[]', required=True)
    context = fields.Text(default='{}', required=True)
    sort = fields.Char(default='[]', required=True)
    model_id = fields.Selection(selection='_list_all_models', string='Model', required=True)
    action_id = fields.Many2one('ir.actions.actions', string='Action', ondelete='cascade',
                                help="The menu action this filter applies to. "
                                     "When left empty the filter applies to all menus "
                                     "for this model.")
    
    

    @api.model
    def _list_all_models(self):
        lang = self.env.lang or 'en_US'
        self.env.cr.execute(
            "SELECT model, COALESCE(name->>%s, name->>'en_US') FROM ir_model ORDER BY 2",
            [lang],
        )
        return self.env.cr.fetchall()
    
    @api.model
    def create_filter(self, vals):
        exist = self.search([('domain','=',vals.get('domain')),('model_id','=',vals.get('model_id'))],limit='1')
        if not exist:
            return self.create({
                'field_name':vals.get('name'),
                'action_id':vals.get('action_id'),
                'model_id':vals.get('model_id'),
                'domain':vals.get('domain'),
                'shared_user_ids':vals.get('user_ids'),
            })
    
    def get_filter_history(self,model):
        records = self.env['filter.search.history'].search(
            [('shared_user_ids', 'in', self.env.user.ids),('model_id','=',model)],
            order='create_date desc',
            limit=10
        )
        return records.read()
    
    @api.model
    def unlink_filter(self,filter):
        filter = self.browse(filter.get('id'))
        if filter:
            filter.unlink() 