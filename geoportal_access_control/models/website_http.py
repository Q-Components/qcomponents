import logging
import ipaddress
from odoo import models, fields
from odoo.http import request
from werkzeug.exceptions import Forbidden

_logger = logging.getLogger(__name__)

class Http(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _dispatch(cls, endpoint):
        if not request or not request.httprequest:
            return super()._dispatch(endpoint)

        path = request.httprequest.path or ""

        if path.startswith(("/web", "/longpolling", "/websocket", "/static")):
            return super()._dispatch(endpoint)

        visitor_ip = request.httprequest.headers.get("X-Forwarded-For",request.httprequest.remote_addr)

        if visitor_ip and "," in visitor_ip:
            visitor_ip = visitor_ip.split(",")[0].strip()

        try:
            ip_obj = ipaddress.ip_address(visitor_ip)
        except ValueError:
            return super()._dispatch(endpoint)

        records = request.env['website.blocked.ip'].sudo().search([('active', '=', True)])

        for rec in records:
            rule = rec.ip_address.strip()
            try:
                if "/" in rule:
                    network = ipaddress.ip_network(rule, strict=False)
                    if ip_obj in network:
                        _logger.warning("Blocked by CIDR rule %s", rule)
                        raise Forbidden("Access denied.")
                else:
                    if ip_obj == ipaddress.ip_address(rule):
                        _logger.warning("Blocked exact IP %s", rule)
                        raise Forbidden("Access denied.")
            except ValueError:
                _logger.warning("Invalid IP rule in DB: %s", rule)
                continue

        return super()._dispatch(endpoint)