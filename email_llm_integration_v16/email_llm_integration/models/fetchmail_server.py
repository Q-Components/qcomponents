from odoo import models,fields
import imaplib
import email
import logging

_logger = logging.getLogger(__name__)

class FetchmailServer(models.Model):

    _inherit = 'fetchmail.server'

    use_for_llm_processing = fields.Boolean(
        string="Use for LLM Email Reading",
        copy=False
    )

    def _fetch_mails(self):
        """
        Fetch unseen emails from servers configured for LLM processing.

        This method connects to all fetchmail servers marked for LLM email reading,
        retrieves unseen emails from the inbox using IMAP (with OAuth authentication
        if applicable), sends the email body to the GPT model for processing, and
        creates corresponding email and processed email records in Odoo.
        """
        self_record = self.env['fetchmail.server'].search([
            ('use_for_llm_processing', '=', True)
        ])
        for server in self_record:
            try:
                # Connect to IMAP
                mail = imaplib.IMAP4_SSL(server.server, server.port)
                server._imap_login(mail)
                mail.select("inbox")

                result, data = mail.search(None, 'UNSEEN')
                email_ids = data[0].split()

                for eid in email_ids:
                    processed_mail = self.env['processed.emails'].search([
                        ('processed_email_id', '=', eid),
                        ('server_id', '=', server.id)
                    ], limit=1)
                    if processed_mail:
                        continue

                    result, data = mail.fetch(eid, '(RFC822)')
                    raw_email = data[0][1]
                    msg = email.message_from_bytes(raw_email)

                    sender = self.env['email.llm'].decode_utf8(msg.get("From"))
                    body = self.env['email.llm'].get_email_body(msg)

                    # Send body to GPT
                    gpt_response = self.env['email.llm'].send_to_gpt(body)
                    if gpt_response:
                        # Create email record
                        email_record = self.env['email.llm'].create({
                            'email_sender_name': sender,
                            'email_body': body,
                        })
                        email_record.gpt_response = gpt_response

                        email_record.process_gpt_product_matches()

                        email_record.create_quotation_from_matched_products()
                        _logger.info(f"Email LLM Model's Record Created Successfully.")

                    self.env['processed.emails'].create({
                        'server_id': server.id,
                        'processed_email_id': eid
                    })
                    mail.store(eid, '-FLAGS', '\\Seen')

            except Exception as e:
                _logger.info(f"Error: {server.name}: {str(e)}")