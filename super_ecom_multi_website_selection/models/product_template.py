from odoo import models, fields, api, _

class product_template(models.Model):
    _inherit = "product.template"

    website_ids = fields.Many2many('website', 'website_product_template_rel', 'product_id', 'website_id', string='Websites')
    
    
    def multi_website_select(self):
        return {
            'name': _('Multi Website Select'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'multi.website.select',
            'context': {'default_product_tmpl_ids':[(6,0,self.ids)]},
            'target': 'new',
        }