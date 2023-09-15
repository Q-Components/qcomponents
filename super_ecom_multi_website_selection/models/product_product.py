from odoo import models, fields, api, _

class product_product(models.Model):
    _inherit = "product.product"

    website_ids = fields.Many2many('website', 'website_product_product_rel', 'product_id', 'website_id', string='Websites', related='product_tmpl_id.website_ids', readonly=False)
    
    
    def multi_website_select(self):
        return {
            'name': _('Multi Website Select'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'multi.website.select',
            'context': {'default_product_ids':[(6,0,self.ids)]},
            'target': 'new',
        }