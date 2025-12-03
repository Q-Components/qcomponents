# -*- coding: utf-8 -*-

import logging
import imaplib
from datetime import datetime
import time
from odoo import api, fields, models
import babel

_logger = logging.getLogger(__name__)

class FetchmailServer(models.Model):
    _inherit = "fetchmail.server"

    user_id = fields.Many2one('res.users', string='Owner')
    mail_server_id = fields.Many2one('mail.server', string="Incoming Provider")
    server = fields.Char(string='Server Name', related='mail_server_id.server',
                         help="Hostname or IP of the mail server")
    port = fields.Integer(string="Port", related='mail_server_id.port')
    type = fields.Selection([
        ('pop', 'POP Server'),
        ('imap', 'IMAP Server'),
        ('local', 'Local Server'),
    ], 'Server Type', related='mail_server_id.type', index=True, default='imap')
    server_type = fields.Selection([
        ('pop', 'POP Server'),
        ('imap', 'IMAP Server'),
        ('local', 'Local Server'),
    ], 'Server Type', related='mail_server_id.type', index=True, default='imap')
    is_ssl = fields.Boolean('SSL/TLS', related='mail_server_id.is_ssl',
                            help="Connections are encrypted with SSL/TLS through a dedicated port (default: IMAPS=993, POP3S=995)")
    last_internal_date = fields.Datetime(
        'Last Fetch Date',
        help="Remote emails with a date greater than this will be "
             "downloaded. Only available with IMAP", default=datetime.now())


    @api.model
    def _fetch_from_date_imap(self, imap_server, count):
        MailThread = self.env['mail.thread']
        failed = 0  # v19: failed should be handled internally
        messages = []
        date_uids = {}
        last_date = False

        last_internal_date = self.last_internal_date

        # normalize month
        month_index = fields.Date.from_string(last_internal_date).month
        month_abbr = babel.dates.get_month_names('abbreviated', locale='en_US')[month_index]
        last_internal_date_str = last_internal_date.strftime('%d-%b-%Y')
        last_internal_date_list = last_internal_date_str.split('-')
        last_internal_date_list[1] = month_abbr
        last_internal_date_str = '-'.join(str(i) for i in last_internal_date_list)

        # IMAP search
        search_status, uids = imap_server.search(
            None,
            'UNSEEN', 'SINCE', '%s' % last_internal_date_str
        )
        new_uids = uids[0].split()
        _logger.info("new_uids : %s Search Status : %s", new_uids, search_status)

        for new_uid in new_uids:
            fetch_status, date = imap_server.fetch(new_uid, 'INTERNALDATE')
            internaldate = imaplib.Internaldate2tuple(date[0])
            internaldate_msg = datetime.fromtimestamp(time.mktime(internaldate))
            if internaldate_msg > last_internal_date:
                messages.append(new_uid)
                date_uids[new_uid] = internaldate_msg

        # Process
        for num in messages:
            result, data = imap_server.fetch(num, '(RFC822)')
            if data and data[0]:
                try:
                    MailThread.message_process(
                        self.object_id.model,
                        data[0][1],
                        save_original=self.original,
                        strip_attachments=(not self.attach)
                    )
                except Exception:
                    _logger.exception('Failed to process mail from IMAP server.')
                    failed += 1

                # mark as seen
                if data[1] and 'Seen' not in data[1].decode('utf-8'):
                    imap_server.store(num, '+FLAGS', '\\Seen')
                else:
                    imap_server.store(num, '-FLAGS', '\\Seen')

                self._cr.commit()
                count += 1

                last_date = date_uids[num] or False
                if last_date:
                    self.write({'last_internal_date': last_date})
                    self._cr.commit()


        return {
            'count': count,
            'failed': failed,
            'last_date': last_date,
        }

    def fetch_mail(self):
        # Fetch Email
        context = self.env.context.copy()
        context['fetchmail_cron_running'] = True
        for server in self:
            _logger.info("Server Type {0} Last Internal Date : {1}".format(server.type,server.last_internal_date))
            if server.type not in ['imap','outlook']:
                super(FetchmailServer, server).fetch_mail()
            elif server.type in ['imap','outlook'] and server.last_internal_date:
                context.update({'fetchmail_server_id': server.id, 'server_type': server.type})

                count, failed = 0, 0
                last_date = False
                imap_server = False
                # Fetch Mail from MailServer
                try:
                    imap_server = server.connect()
                    imap_server.select()
                    count, failed, last_date = server.with_context(**context)._fetch_from_date_imap(imap_server, count
                                                                                                    )
                except Exception:
                    _logger.exception("General failure when trying to fetch mail by date from %s server %s.",
                                      server.type, server.name)
                finally:
                    if imap_server:
                        imap_server.close()
                        imap_server.logout()
                if last_date:
                    vals = {'last_internal_date': last_date}
                    if 'server_type' in vals:
                        vals.pop('server_type')
                    if 'is_ssl' in vals:
                        vals.pop('is_ssl')
                    server.write(vals)
                    self._cr.commit()
        return

    # @api.model
    # def _fetch_mails(self):
    #     """ Method called by cron to fetch mails from servers """
    #     return self.search([('state', '=', 'done'), ('type', 'in', ['pop', 'imap'])]).fetch_mail()
