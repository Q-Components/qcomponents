from odoo import models, fields
from odoo.http import request
from werkzeug.exceptions import Forbidden
from odoo.addons.base.models.ir_http import IrHttp
import logging
_logger = logging.getLogger(__name__)

class WebsiteVisitor(models.Model):
    _inherit = "website.visitor"

    user_ip = fields.Char("Visitor IP", index=True)

    def _upsert_visitor(self, access_token, force_track_values=None):
        ip = None
        if request:
            ip = request.httprequest.headers.get('X-Forwarded-For', request.httprequest.remote_addr)

        visitor_id, action = super()._upsert_visitor(access_token,force_track_values=force_track_values)
        if visitor_id and ip and action == 'inserted':
            self.env.cr.execute("UPDATE website_visitor SET user_ip=%s WHERE id=%s",(ip, visitor_id))

        return visitor_id, action