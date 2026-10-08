# -*- coding: utf-8 -*-
import logging
import time

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class SkuvaultInventoryBatch(models.Model):
    _name = 'skuvault.inventory.batch'
    _description = 'Skuvault Inventory Batch'
    _order = 'id'

    name = fields.Char(string="Batch", readonly=True, copy=False)
    warehouse_id = fields.Many2one('stock.warehouse', string="Warehouse", index=True, ondelete='cascade')
    state = fields.Selection([('pending', 'Pending'), ('done', 'Done'), ('failed', 'Failed')],
                             string="Status", default='pending', index=True, copy=False)
    line_ids = fields.One2many('skuvault.inventory.batch.line', 'batch_id', string="Products")
    total_count = fields.Integer(compute='_compute_counts')
    failed_count = fields.Integer(compute='_compute_counts')
    processed_on = fields.Datetime(string="Processed On", readonly=True, copy=False)

    @api.depends('line_ids.state')
    def _compute_counts(self):
        for batch in self:
            batch.total_count = len(batch.line_ids)
            batch.failed_count = len(batch.line_ids.filtered(lambda l: l.state == 'failed'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['name'] = self.env['ir.sequence'].next_by_code('skuvault.inventory.batch') or '/'
        return super().create(vals_list)

    def _process_batch(self):
        self.ensure_one()
        warehouse = self.warehouse_id
        location = warehouse.lot_stock_id
        Quant = self.env['stock.quant']

        pending_deliveries = self.env['stock.picking'].search([
            ('picking_type_code', '=', 'outgoing'),
            ('state', 'in', ('assigned')),
            ('picking_type_id.warehouse_id', '=', warehouse.id),
        ])
        delivery_pending_product_ids = pending_deliveries.move_ids.product_id.ids or []

        for line in self.line_ids.filtered(lambda l: l.state == 'pending'):
            product = self.env['product.product'].search([('default_code', '=', line.sku)], limit=1)
            if not product:
                line.write({'state': 'failed', 'error_message': _("Product not found in Odoo.")})
                continue

            if product.id not in delivery_pending_product_ids and location:
                new_quantity = float(line.available_qty or 0.0)
                stock_quant = Quant.search([('product_id', '=', product.id),
                                            ('location_id', '=', location.id)], limit=1)
                if stock_quant:
                    # inventory present: update it
                    stock_quant.update({'inventory_quantity': new_quantity})
                    stock_quant.action_apply_inventory()
                else:
                    # inventory not present: create it
                    Quant.create({
                        'location_id': location.id,
                        'product_id': product.id,
                        'inventory_quantity': new_quantity,
                    }).action_apply_inventory()
                line.write({'state': 'done', 'product_id': product.id, 'error_message': False})
            else:
                line.write({'state': 'failed', 'product_id': product.id,
                            'error_message': _("Inventory not updated: product is in an assigned delivery.")})

        self.write({
            'state': 'failed' if self.line_ids.filtered(lambda l: l.state == 'failed') else 'done',
            'processed_on': fields.Datetime.now(),
        })

    def action_retry_failed(self):
        for batch in self:
            batch.line_ids.filtered(lambda l: l.state == 'failed').write({'state': 'pending', 'error_message': False})
            batch.state = 'pending'

    def action_process_batch(self):
        for batch in self.filtered(lambda b: b.state == 'pending'):
            batch._process_batch()

    @api.model
    def cron_process_batches(self, time_limit=100):
        """CRON 2: update Odoo inventory batch wise. Only 'pending' batches are picked,
        so finished batches (and their products) are never synced again."""
        start = time.time()
        batches = self.search([('state', '=', 'pending')],limit=50)
        for batch in batches:
            if time.time() - start > time_limit:
                break
            try:
                batch._process_batch()
                self.env.cr.commit()
            except Exception as error:
                self.env.cr.rollback()
                _logger.error("Skuvault batch %s failed: %s", batch.id, error)


class SkuvaultInventoryBatchLine(models.Model):
    _name = 'skuvault.inventory.batch.line'
    _description = 'Skuvault Inventory Batch Line'
    _order = 'id'

    batch_id = fields.Many2one('skuvault.inventory.batch', string="Batch", index=True, ondelete='cascade')
    warehouse_id = fields.Many2one('stock.warehouse', string="Warehouse", index=True, ondelete='cascade')
    sku = fields.Char(string="SKU", index=True)
    available_qty = fields.Float(string="SkuVault Qty")
    product_id = fields.Many2one('product.product', string="Product", ondelete='set null')
    state = fields.Selection([('pending', 'Pending'), ('done', 'Done'), ('failed', 'Failed')],
                             string="Status", default='pending', index=True)
    error_message = fields.Char(string="Error")

    _sku_warehouse_uniq = models.Constraint(
        'unique(warehouse_id, sku)', 'This SKU is already queued for this warehouse.')
