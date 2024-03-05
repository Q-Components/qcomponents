from odoo import models, fields


class ShopifyRiskOrder(models.Model):
    _name = "shopify.risk.order"
    _description = 'Shopify Risk Order'

    name = fields.Char(string="Order Id", required=True)
    order_risk_id = fields.Char(string="Order Risk ID")
    cause_cancel = fields.Boolean(string="Cause Cancel", default=False)
    display = fields.Boolean(string="Display", default=False)
    message = fields.Text(string="Message")
    recommendation = fields.Selection(selection=[('accept', 'This check found no indication of fraud'),
                                                 ('investigate',
                                                  'This order might be fraudulent and needs further investigation'),
                                                 ('cancel', 'This order should be cancelled by the merchant')],
                                      default='accept')
    score = fields.Float(string="score")
    source = fields.Char(string="source")
    odoo_order_id = fields.Many2one("sale.order", string="Order")

    def shopify_create_risk_in_sale_order(self, risk_result, order):
        """
        This method used to create a risk order, if found risk in Shopify order when import orders from Shopify to Odoo.
        """
        for risk_id in risk_result:
            risk = risk_id.to_dict()
            vals = self.prepare_vals_for_order_risk(risk, order)
            self.create(vals)
        return True

    def prepare_vals_for_order_risk(self, risk, order):
        """
        This method is used to prepare a vals for the creation record of risk order.
        """
        vals = {'name': risk.get('order_id'),
                'order_risk_id': risk.get('id'),
                'cause_cancel': risk.get('cause_cancel'),
                'display': risk.get('display'),
                'message': risk.get('message'),
                'recommendation': risk.get('recommendation'),
                'score': risk.get('score'),
                'source': risk.get('source'),
                'odoo_order_id': order.id
                }
        return vals
