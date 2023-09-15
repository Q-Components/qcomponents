from odoo import models, fields, api, _

class multi_website_select(models.TransientModel):
    _inherit = "multi.website.select"

    product_tmpl_ids = fields.Many2many('product.template', 'multi_website_select_product_template_rel', 'multi_website_select_id', 'product_tmpl_id', string='Product Template')
    product_ids = fields.Many2many('product.product', 'multi_website_select_product_product_rel', 'multi_website_select_id', 'product_id', string='Product')
    ecateg_ids = fields.Many2many('product.public.category', 'multi_website_select_ecateg_rel', 'multi_website_select_id', 'ecateg_id', string='eCateg')
    

    def process(self):
        if self.product_tmpl_ids:
            for product_tmpl in self.product_tmpl_ids:
                product_tmpl.website_ids = [(6,0,self.website_ids.ids)]
        if self.product_ids:
            for product in self.product_ids:
                product.website_ids = [(6,0,self.website_ids.ids)]
        if self.ecateg_ids:
            for ecateg in self.ecateg_ids:
                ecateg.website_ids = [(6,0,self.website_ids.ids)]
        return super(multi_website_select, self).process()
        