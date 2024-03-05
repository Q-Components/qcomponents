from odoo import models, fields


class OrderWorkflowAutomation(models.Model):
    _name = 'order.workflow.automation'
    _description = 'Order Workflow Automation'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name', help='Enter Name', copy=False, tracking=True)
    company_id = fields.Many2one('res.company', string='Company', help='Select Company',
                                 copy=False, tracking=True, default=lambda self: self.env.user.company_id)
    journal_id = fields.Many2one('account.journal', string='Journal', help='Select Journal',
                                 copy=False, tracking=True)
    confirm_sale_order = fields.Boolean(string='Confirm Sale Order',
                                        help='Enable this option if you want to confirm sale order',
                                        copy=False, tracking=True)
    create_invoice = fields.Boolean(string='Invoice',
                                    help='Enable this option if you want to Create Invoice & Validate',
                                    copy=False, tracking=True)
    validate_delivery_order = fields.Boolean(string='Validate Delivery Order',
                                             help='Enable this option if you want to validate delivery order',
                                             copy=False, tracking=True)
    policy_of_picking = fields.Selection(
        [('direct', 'Deliver each product when available'), ('one', 'Deliver all product at once')],
        string='Shipping Policy', help='Select Picking Policy', copy=False, tracking=True)
