from odoo import models, fields, api
import datetime

class SkuvaultOperation(models.Model):
    _name = "skuvault.operation"
    _order = 'id desc'
    _inherit = ['mail.thread']

    name = fields.Char("Name")
    skuvault_operation = fields.Selection([('product', 'Product')], string="Skuvault Operation")
    skuvault_operation_type = fields.Selection([('export', 'Export'),
                                       ('import', 'Import'),
                                       ('update', 'Update'),
                                       ('delete', 'Cancel / Delete')], string="Skuvault Operation Type")
    warehouse_id = fields.Many2one("stock.warehouse", "Warehouse")
    company_id = fields.Many2one("res.company", "Company")
    operation_ids = fields.One2many("skuvault.operation.details", "operation_id",string="Operation")
    skuvault_message = fields.Char("Message")

    @api.model
    def create(self, vals):
        sequence = self.env.ref("skuvault_odoo_integration.seq_skuvault_operation_detail")
        name = sequence and sequence.next_by_id() or '/'
        company_id = self._context.get('company_id', self.env.user.company_id.id)
        if type(vals) == dict:
            vals.update({'name': name, 'company_id': company_id})
        return super(SkuvaultOperation, self).create(vals)


class SkuvaultOperationDetail(models.Model):
    _name = "skuvault.operation.details"
    _rec_name = 'operation_id'
    _order = 'id desc'
    
    operation_id = fields.Many2one("skuvault.operation", string="Skuvault Operation")
    skuvault_operation = fields.Selection([('product','Product')], string="Operation")
    skuvault_operation_type = fields.Selection([('export', 'Export'),
                                       ('import', 'Import'),
                                       ('update', 'Update'),
                                       ('delete', 'Cancel / Delete')], string="Skuvault operation Type")

    warehouse_id = fields.Many2one("stock.warehouse", "Warehouse", related="operation_id.warehouse_id")
    company_id = fields.Many2one("res.company", "Company")
    request_message = fields.Char("Request Message")
    response_message = fields.Char("Response Message")
    fault_operation = fields.Boolean("Fault Operation", default=False)
    process_message=fields.Char("Message")    
    
    @api.model
    def create(self, vals):
        if type(vals) == dict:
            operation_id = vals.get('operation_id')
            operation = operation_id and self.env['skuvault.operation'].browse(operation_id) or False
            company_id = operation and operation.company_id.id or self.env.user.company_id.id
            vals.update({'company_id': company_id})
        return super(SkuvaultOperationDetail, self).create(vals)
