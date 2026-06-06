from odoo import api, fields, models
from datetime import date
from odoo.exceptions import ValidationError

class PaymentWizard(models.TransientModel):
    _name = 'payment.wizard'
    _description = 'Payment Wizard'

    journal_id = fields.Many2one(comodel_name='account.journal', string="Journal",
                                default=lambda self: self.env['account.journal'].search([('type', '=', 'bank')],
                                                                                        limit=1))
    payment_method_line_id = fields.Many2one(comodel_name='account.payment.method.line', string='Payment Method',
                                             domain="[('id', 'in', available_payment_method_line_ids)]",
                                             default=lambda self: self.env['account.payment.method.line'].search([],limit=1))
    available_payment_method_line_ids = fields.Many2many('account.payment.method.line',
                                                         compute='_compute_payment_method_line_fields',
                                                         help="for adding domain", store=True)
    partner_bank_id = fields.Many2one(comodel_name='res.partner.bank', string='Recipient Bank Account')
    company_id = fields.Many2one('res.company', store=True, copy=False,string="Company",
                                 default=lambda self: self.env.user.company_id.id)
    currency_id = fields.Many2one('res.currency', string="Currency",related='company_id.currency_id',
                                  default=lambda self: self.env.user.company_id.currency_id.id)
    amount = fields.Monetary(string='Amount')
    payment_date = fields.Date(string='Payment Date', required=True, default=date.today())
    communication = fields.Char(string='Memo')
    payment_token_id = fields.Many2one(comodel_name='payment.token', string="Saved payment token")

    @api.model
    def default_get(self, fields):
        res = super(PaymentWizard, self).default_get(fields)
        active_id = self.env.context.get('active_id')
        ord = self.env['sale.order'].browse(active_id)
        res['amount'] = ord.total_order_amount if ord else 0
        res['currency_id'] = ord.pricelist_id.currency_id.id
        return res

    @api.depends('journal_id', 'currency_id')
    def _compute_payment_method_line_fields(self):
        for rec in self:
            if rec.journal_id:
                rec.available_payment_method_line_ids = rec.journal_id.inbound_payment_method_line_ids.ids
            else:
                rec.available_payment_method_line_ids = False

    def action_create_payment(self):
        active_id = self.env.context.get('active_id')
        ord = self.env['sale.order'].browse(active_id)

        if self.amount > ord.total_order_amount:
            raise ValidationError("The entered amount cannot exceed the total order amount !!")
        if self.amount <= 0:
            raise ValidationError("Payment cannot be created with a negative or zero amount.")
        payment_vals = {
            'amount': self.amount,
            'date': self.payment_date,
            'payment_method_line_id': self.payment_method_line_id.id,
            'journal_id': self.journal_id.id,
            'currency_id': ord.pricelist_id.currency_id.id,
            'memo': self.communication,
            'payment_type': 'inbound',
            'partner_id': ord.partner_id.id
        }

        # Create the payment
        payment = self.env['account.payment'].create(payment_vals)

        # Post the payment
        payment.action_post()
        ord.total_order_amount -= self.amount
        ord.write({'total_order_amount': ord.total_order_amount})