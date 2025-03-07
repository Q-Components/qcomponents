import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class FetchmailOutlookServer(models.Model):
    _inherit = "fetchmail.server"

    mail_server_id = fields.Many2one('mail.server', string="Incoming Provider")
    server = fields.Char(string='Server Name', related='mail_server_id.server',
                         help="Hostname or IP of the mail server")
    type = fields.Selection(selection_add=[('outlook', 'Outlook OAuth Authentication'), ]
                            , related='mail_server_id.type', index=True, default='imap')
    server_type = fields.Selection(selection_add=[('outlook', 'Outlook OAuth Authentication'), ]
                                   , related='mail_server_id.type', index=True, ondelete={'outlook': 'set default'})

    @api.model
    def _fetch_from_date_imap(self, imap_server, count, failed):
        super(FetchmailOutlookServer, self)._fetch_from_date_imap()
