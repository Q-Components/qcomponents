from odoo import models, fields


class ShopifyFinancialStatusConfiguration(models.Model):
    _name = 'shopify.financial.status.configuration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Shopify Financial Status Configuration'

    instance_id = fields.Many2one('shopify.instance.integration', string='Instance', help='Select Instance')
    company_id = fields.Many2one('res.company', string='Company', help='Select Company', default=lambda self: self.env.user.company_id)
    payment_gateway_id = fields.Many2one('shopify.payment.gateway', string='Payment Gateway',
                                         help='Select Payment')
    payment_term_id = fields.Many2one('account.payment.term', string='Payment Term', help='Select Payment Term',
                                      default=lambda self: self.env.ref('account.account_payment_term_immediate'))
    sale_auto_workflow_id = fields.Many2one('order.workflow.automation', string='Auto Workflow',
                                            help='Select Workflow')
    active = fields.Boolean(string='Active', default=True)
    financial_status = fields.Selection([
        ('pending', ' The finances are pending'),
        ('authorized', 'The finances have been authorized'),
        ('partially_paid', 'The finances have been partially paid'),
        ('paid', 'The finances have been paid'),
        ('partially_refunded', 'The finances have been partially refunded'),
        ('refunded', 'The finances have been refunded'),
        ('voided', 'The finances have been voided')
    ], string='Financial Status', help='Select Financial Status')

    def create_shopify_financial_status(self, instance, shopify_financial_status):
        """
        Creates shopify financial status for payment methods of instance.
        @param instance: shopify_instance
        @param shopify_financial_status: Status as paid or not paid.
        """
        payment_methods = self.env['shopify.payment.gateway'].search([('instance_id', '=', instance.id)])
        journal_id = self.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', self.env.company.id)], limit=1)

        auto_workflow_obj = self.env['order.workflow.automation']
        auto_workflow_id = auto_workflow_obj.search([('name', '=', 'Automatic Validation')])
        if not auto_workflow_id:
            auto_workflow_id = auto_workflow_obj.create({
                'name': 'Automatic Validation',
                'journal_id': journal_id.id,
                'company_id': instance.company_id.id
            })

        for payment_method in payment_methods:
            # Check record already exist or not
            existing_shopify_financial_status = self.search([('instance_id', '=', instance.id),
                                                             ('payment_gateway_id', '=', payment_method.id),
                                                             ('financial_status', '=', shopify_financial_status)]).ids
            if existing_shopify_financial_status:
                continue

            # Create new record based on payment methods
            self.create({
                'instance_id': instance.id,
                'sale_auto_workflow_id': auto_workflow_id.id,
                'payment_gateway_id': payment_method.id,
                'financial_status': shopify_financial_status,
                'company_id': instance.company_id.id
            })
        return True
