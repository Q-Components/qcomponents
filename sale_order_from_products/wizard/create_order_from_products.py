from odoo import fields, models


class CreateOrderFromProducts(models.TransientModel):
    _name = "create.order.from.products"
    _description = "From products sale order create"

    partner_id = fields.Many2one('res.partner', string='Contact / Customer')

    def create_order_from_products(self):
        """
        From this method selected products set as sale order line & new sale order created.
        """
        product_records = self.env['product.product'].browse(self._context.get('active_ids', []))
        if product_records:
            sale_order = self.env['sale.order'].create({
                        'partner_id': self.partner_id.id,
                    })
            if sale_order:
                sale_order_line = self.env['sale.order.line']
                for product in product_records:
                    order_line = {
                        'order_id': sale_order.id,
                        'product_id': product.id,
                        'name': product.display_name or product.name,
                        'product_uom_qty': 1,
                        'product_uom': product.uom_id.id,
                        'price_unit': product.lst_price,
                    }
                    sale_order_line.create(order_line)
                return {
                    'name': 'Sale Order',
                    'view_mode': 'form',
                    'res_model': 'sale.order',
                    'domain': [],
                    'res_id': sale_order.id,
                    'view_id': False,
                    'type': 'ir.actions.act_window',
                    'context': {}
                }
