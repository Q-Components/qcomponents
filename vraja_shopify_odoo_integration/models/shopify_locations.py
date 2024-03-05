import time
from odoo import models, fields
from .. import shopify
from ..shopify.pyactiveresource.connection import ClientError


class ShopifyLocations(models.Model):
    _name = 'shopify.location'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Shopify Locations'

    name = fields.Char(string='Name', help='Enter Name', copy=False, tracking=True)
    active = fields.Boolean(default=True)
    shopify_location_id = fields.Char(string='Shopify Location', help='Location ID', copy=False, tracking=True)
    instance_id = fields.Many2one('shopify.instance.integration', string='Instance',
                                  help='Select Instance Id', copy=False, tracking=True)
    company_id = fields.Many2one('res.company', string='Company', help='Select Company',
                                 copy=False, tracking=True, default=lambda self: self.env.user.company_id)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', help='Select Warehouse',
                                   copy=False, tracking=True)
    export_stock_warehouse_ids = fields.Many2many('stock.warehouse', string='Warehouses')
    is_primary_location = fields.Boolean(string='Is Primary Location', copy=False,
                                         help='From shopify shop if any location found '
                                              'then set that location as primary location', tracking=True)
    legacy = fields.Boolean('Is Legacy Location',
                            help="If true, then the location is a fulfillment service location. "
                                 "If false, then the location was created by the merchant and isn't "
                                 "tied to a fulfillment service.")
    is_import_stock = fields.Boolean(string='Stock',
                                     help='If you enable then stock for this location will be use for import.',
                                     copy=False, tracking=True, default=True)
    location_id = fields.Many2one('stock.location', string='Location', copy=False, tracking=True)

    def import_shopify_locations(self, instance):
        """
        Retrieve all the locations from the Shopify instance after confirming the connection from Odoo.
        """
        log_id = self.env['shopify.log'].generate_shopify_logs('location', 'import', instance, 'Process Started')
        self._cr.commit()
        instance_id = instance.id
        shopify_location_list = []
        try:
            locations = shopify.Location.find()
        except ClientError as error:
            if hasattr(error, "response") and error.response.code == 429 and error.response.msg == "Too Many Requests":
                time.sleep(int(float(error.response.headers.get('Retry-After', 5))))
                locations = shopify.Location.find()
        except Exception as error:
            error_msg = 'Getting Some Error When Try To Import Location From Shopify To Odoo'
            self.env['shopify.log.line'].generate_shopify_process_line('location', 'import', instance, error_msg,
                                                                       False, error, log_id, True)
        for location in locations:
            location = location.to_dict()
            vals = self.prepare_vals_for_location(location, instance)
            shopify_location = self.search(
                [('shopify_location_id', '=', location.get('id')), ('instance_id', '=', instance_id)])
            if shopify_location:
                shopify_location.write(vals)
                msg = "Location Already Exist {}".format(shopify_location and shopify_location.name)
                self.env['shopify.log.line'].generate_shopify_process_line('location', 'import', instance, msg,
                                                                           False, location, log_id, False)
            else:
                shopify_location = self.create(vals)
                msg = "Location Successfully Created {}".format(shopify_location and shopify_location.name)
                self.env['shopify.log.line'].generate_shopify_process_line('location', 'import', instance, msg,
                                                                           False, location, log_id, False)
            shopify_location_list.append(shopify_location.id)
        log_id.shopify_operation_message = 'Process Has Been Finished'
        if not log_id.shopify_operation_line_ids:
            log_id.unlink()
        return shopify_location_list

    def prepare_vals_for_location(self, location, instance):
        """
        This method is used to prepare a location vals.
        """
        values = {
            'name': location.get('name'),
            'shopify_location_id': location.get('id'),
            'instance_id': instance and instance.id,
            'company_id': instance and instance.company_id.id,
            'warehouse_id': instance and instance.warehouse_id.id,
            'location_id': instance and instance.warehouse_id.lot_stock_id.id,
            'legacy': location.get('legacy')
        }
        return values
