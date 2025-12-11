import logging
import requests
from odoo import models, fields

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    ups_cod_amount = fields.Char("UPS COD Amount", help="UPS COD Price", readonly=True, copy=False)
    document_id = fields.Char("DocumentID", help="Forms History Document ID", readonly=True, copy=False)
    ups_paperless_invoice = fields.Boolean("UPS Paperless Invoice", help="True if you need to Ups Paperless Invoice")
    shipment_status = fields.Char(string="Shipment Status")

    def generate_paperless_invoice(self):
        return self.carrier_id.ups_paperless_invoice_provider(self)

    def ups_shipment_status(self):
        picking_obj = self.search([('carrier_tracking_ref', '!=', ''), ('shipment_status', '!=', 'Delivered'),('delivery_type','=','ups_provider')])
        for picking in picking_obj:
            url = "{0}/api/track/v1/details/{1}".format(picking.company_id and picking.company_id.ups_api_url,
                                                        picking.carrier_tracking_ref)
            payload = ""
            headers = {
                'transId': 'UPS',
                'transactionSrc': 'UPS',
                'Authorization': 'Bearer {0}'.format(picking.company_id and picking.company_id.ups_api_token),
            }
            try:
                response = requests.request("GET", url, headers=headers, data=payload)
                if response.status_code == 200:
                    tracking_response = response.json()
                    shipment_rec = tracking_response.get('trackResponse').get('shipment')
                    for shipment in shipment_rec:
                        package_rec = shipment.get('package')
                        if package_rec:
                            for package in package_rec:
                                picking.shipment_status = package.get('currentStatus').get('description')
                                picking._cr.commit()
                            _logger.info("UPS Shipment Status Get Successfully.")
            except Exception as e:
                _logger.info("UPS Shipment Status {0}".format(e))
