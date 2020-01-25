# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class ReturnOrder(models.Model):
    _name = 'return.order'
    _rec_name = 'number'
    _order = 'id desc'
#    _inherit = ['mail.thread', 'ir.needaction_mixin']
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin'] #odoo11
    _description = "Return Order"
    
    number = fields.Char(
        string="Number"
    )
    state = fields.Selection(
        [('draft','Draft'),
         ('confirm','Confirmed'),
         ('approve','Approved'),
         ('return','Return'),
         ('cancel','Cancelled')],
        track_visibility='onchange',
        default='draft',
        copy=False, 
    )
    partner_id = fields.Many2one(
        'res.partner',
        string="Customer",
        required = True,
    )
    saleorder_id = fields.Many2one(
        'sale.order',
        string="Sale Order",
        required = True,
    )
    product_id = fields.Many2one(
        'product.product',
        string="Return Product",
        required = True,
    )
    quantity = fields.Float(
        string="Return Quantity",
        required = True,
    )
    reason = fields.Text(
        string="Reason",
        required = True,
    )
    saleorderline_id = fields.Many2one(
        'sale.order.line',
        string="Sale Order Line",
        readonly=True,
    )
    delivery_ids = fields.Many2many(
        'stock.picking',
        string="Customers Delivery Order",
        compute='_compute_picking_delivery',
    )
    incoming_delivery_ids = fields.One2many(
        'stock.picking',
        'rma_order_id',
        domain =[('picking_type_code', '=', 'incoming')],
        string="Vendors Delivery Order",
    )
    confirm_by = fields.Many2one(
        'res.users',
        string='Confirmed By',
        readonly = True,
    )
    confirm_date = fields.Date(
        string='Confirmed Date',
        readonly = True,
    )
    approve_by = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly = True,
    )
    approve_date = fields.Date(
        string='Aproved Date',
        readonly = True,
    )
    create_date = fields.Date(
        string='Create Date',
        default=fields.date.today(),
        required = True,
    )
    return_by = fields.Many2one(
        'res.users',
        string='Return By',
        readonly = True,
    )
    return_date = fields.Date(
        string='Return Date',
        readonly = True,
    )
    # uom_id = fields.Many2one(
    #     'product.uom',
    #     string='Uom',
    #     compute='compute_set_uom',
    #     required = True,
    # )
    uom_id = fields.Many2one(
        'uom.uom',
        string='Uom',
        compute='compute_set_uom',
        required = True,
    )
    company_id = fields.Many2one(
        'res.company',
        required = True,
        default=lambda self: self.env.user.company_id,
        string='Company',
    )
    salesperson_id = fields.Many2one(
        'res.users',
        string='Salesperson',
    )
    team_id = fields.Many2one(
        'crm.team',
        string='Sales Team',
    )
    notes = fields.Text(
        'Add comment'
    )
    order_partner_id = fields.Many2one(
        'res.partner',
        string = "Order Customer",
        related = 'saleorder_id.partner_id',
        readonly = True,
    )
    incoming_delivery_count = fields.Integer(
        compute="_incoming_delivery_count",
    )
    outgoing_delivery_count = fields.Integer(
        compute="_outgoing_delivery_count",
    )

#    @api.multi odoo13
    @api.depends()
    def _incoming_delivery_count(self):
        for rec in self:
            rec.incoming_delivery_count = self.env['stock.picking'].search_count([
                ('rma_order_id', '=', rec.id),
                ('picking_type_code', '=', 'incoming')
            ])
           
    
#    @api.multi odoo13
    def action_view_incoming_delivery(self):
        for rec in self:
            delivery_id = self.env['stock.picking'].search([
                        ('rma_order_id', '=', rec.id),
                        ('picking_type_code', '=', 'incoming') 
            ])
        action = self.env.ref('stock.action_picking_tree_all')
        result = action.read()[0]
        result['domain'] = [('id', 'in', delivery_id.ids)]
        return result
    
#    @api.multi odoo13
    @api.depends()
    def _outgoing_delivery_count(self):
        for rec in self:
            rec.outgoing_delivery_count = self.env['stock.picking'].search_count([
                ('sale_id', '=', rec.saleorder_id.id),
                ('picking_type_code', '=', 'outgoing')
            ])

#    @api.multi odoo13
    def action_view_outgoing_delivery(self):
        for rec in self:
            delivery_id = self.env['stock.picking'].search([
                        ('sale_id', '=', rec.saleorder_id.id),
                        ('picking_type_code', '=', 'outgoing') 
            ])
        action = self.env.ref('stock.action_picking_tree_all')
        result = action.read()[0]
        result['domain'] = [('id', 'in', delivery_id.ids)]
        return result
    
    @api.model
    def create(self, vals):
        number = self.env['ir.sequence'].next_by_code('return.rma.seq')
        vals.update({
            'number': number,
            'return_by': self.env.user.id,
            'return_date' : fields.Date.today(),
            })
        res = super(ReturnOrder, self).create(vals)
        return res
        
#    @api.multi odoo13
    def return_confirm(self):
        for rec in self:
            rec.confirm_by = self.env.user.id
            rec.confirm_date = fields.Date.today()
            rec.state = 'confirm'
            
#    @api.multi odoo13
    def return_done(self):
        for rec in self:
            rec.state = 'return'
        
#    @api.multi odoo13
    def return_cancel(self):
        for rec in self:
            rec.state = 'cancel'
            
#    @api.multi odoo13
    def reset_draft(self):
        for rec in self:
            rec.state = 'draft'
            
#    @api.multi odoo13
    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('You can not delete this record.'))
        return super(ReturnOrder, self).unlink()

#    @api.multi odoo13
    def _compute_picking_delivery(self):
        for rec in self:
            rec.delivery_ids = self.env['stock.picking'].search([
                                        ('sale_id', '=', rec.saleorder_id.id),
                                        ('picking_type_code', '=', 'outgoing') 
                                    ])
    
#    @api.multi odoo13
    def _compute_incoming_picking_delivery(self):
        for rec in self:
            rec.incoming_delivery_ids = self.env['stock.picking'].search([
                                        ('sale_id', '=', rec.saleorder_id.id),
                                        ('picking_type_code', '=', 'incoming') 
                                    ])
            
            
#    @api.multi odoo13
    def return_approve(self):
        for rec in self:
            rec.approve_by = self.env.user.id
            rec.approve_date = fields.Date.today()
            rec.state = 'approve'
            
#    @api.multi odoo13
    @api.depends('product_id')
    def compute_set_uom(self):
        for rec in self:
            rec.uom_id = rec.product_id.uom_id.id

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
