from odoo import models, fields, api, _
from odoo.http import request

class website_multi_mixin(models.AbstractModel):
    _inherit = "website.multi.mixin"

    def can_access_from_current_website(self, website_id=False):
        res = super(website_multi_mixin, self).can_access_from_current_website(website_id)
        if self._name == 'product.template':
            res = True
            if self.website_ids:
                if request.website.id in self.website_ids.ids:
                    res = True
                else:
                    res = False
        if self._name == 'product.public.category':
            res = True
            website_ids = []
            categ = self
            while categ:
                website_ids += categ.website_ids.ids
                categ = categ.parent_id
            website_ids = list(set(website_ids))
            if website_ids:
                if request.website.id in website_ids:
                    res = True
                else:
                    res = False
        return res

    
    
