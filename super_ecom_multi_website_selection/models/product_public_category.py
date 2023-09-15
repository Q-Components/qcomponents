from odoo import models, fields, api, _

class product_public_category(models.Model):
    _inherit = "product.public.category"

    website_ids = fields.Many2many('website', 'website_product_public_category_rel', 'ecom_id', 'website_id', 'Websites')
    
    def multi_website_select(self):
        return {
            'name': _('Multi Website Select'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'multi.website.select',
            'context': {'default_ecateg_ids':[(6,0,self.ids)]},
            'target': 'new',
        }

    @api.onchange('parent_id','parent_id.website_ids','website_ids')
    def onchange_Parent(self):
        self.ensure_one()
        domain = []
        if self.parent_id and self.parent_id.website_ids:
            domain.append(('id','in',self.parent_id.website_ids.ids))
            if self.website_ids:
                website_ids = self.website_ids.ids
                for website in self.website_ids:
                    if website._origin.id not in self.parent_id.website_ids.ids:
                        website_ids.remove(website._origin.id)
                if len(self.website_ids) != website_ids:
                    self.website_ids = [(6,0,website_ids)]
        return {'domain':{'website_ids':domain}}
    
