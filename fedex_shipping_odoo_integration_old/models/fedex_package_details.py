from odoo import models, fields,api

class FedExPackageDetails(models.Model):
    _name= "fedex.package.details"
    
    stock_picking_id=fields.Many2one('stock.picking',string="Picking ID")
    sale_order_id=fields.Many2one('sale.order',string="sale ID")
    shipping_weight=fields.Float(string="Shipping Weight",help="Shipping Weight consider total package weight")
    width=fields.Integer(string="Width")
    length= fields.Integer(string="Length")
    height= fields.Integer(string="Height")