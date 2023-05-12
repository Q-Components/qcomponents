from odoo import api, fields, models, _


class ProductProduct(models.Model):
    _inherit = "product.product"

    x_studio_field_2dpeg = fields.Float(string='Quotation Price', digits='Product Price')
    sku_location = fields.Char(string='Sku Location')
    x_studio_condition_1 = fields.Char(string='Condition')
    supplier_name = fields.Char(string='Supplier Name')

    def action_create_saleorder_from_product(self):
        product_ids = self._context.get('active_ids')
        action = self.env.ref("sale.action_orders").read()[0]
        res = self.env.ref('sale.view_order_form', False)
        action['views'] = [(res and res.id or False, 'form')]
        records = self.browse(product_ids)
        action['context'] = {
            'default_order_line': [(0, 0, {'product_id': r.id, 'product_template_id': r.product_tmpl_id.id}) for r in
                                   records]}
        return action
