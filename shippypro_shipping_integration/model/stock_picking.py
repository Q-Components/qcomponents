import binascii
from odoo.exceptions import ValidationError
from odoo import fields, models, api


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    shippypro_order_id = fields.Char(string="Shippypro Order Id", copy=False)
    shippypro_tracking_url = fields.Char(string="Shippypro Tracking URL")

    def generate_label_shippypro(self):
        label_response = self.carrier_id and self.carrier_id.generate_label_using_order_id(self.shippypro_order_id)
        label_data = label_response and label_response.get('PDF')
        if label_data:
            for data in label_data:
                data = binascii.a2b_base64(str(data))
                message = ((
                               "Label created!<br/> <b>Order  Number : </b>%s<br/>") % (
                               self.shippypro_order_id,))
                self.message_post(body=message, attachments=[
                    ('Shippypro-%s.%s' % (self.shippypro_order_id, "pdf"), data)])
            tracking_number = label_response.get('TrackingNumber')
            tracking_url = label_response.get('TrackingExternalLink')
            self.shippypro_tracking_url = tracking_url
            self.carrier_tracking_ref = tracking_number
        else:
            raise ValidationError(str(label_response))
