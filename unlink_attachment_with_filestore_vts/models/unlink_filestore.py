import os
from odoo import models, fields
from odoo.exceptions import ValidationError


class UnlinkFilestore(models.Model):
    _name = 'unlink.filestore'
    _description = "Unlink Filestore"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'analytic.mixin']
    _rec_name = 'model_id'

    model_id = fields.Many2one(comodel_name='ir.model', string="Model Name")
    mime_type = fields.Char(string="Mime Type", help="Set file format.")
    before_date = fields.Date(string="Before Date", help="Takes the data before the entered date.")
    after_date = fields.Date(string="After Date", help="Takes the data after the entered date.")
    only_today_date = fields.Date(string="Only Today Date", help="Takes the data of only today's date.",
                                  default=fields.Date.today())
    from_date = fields.Date(string="From Date", help="Select from date.")
    to_date = fields.Date(string="To Date", help="Select to date.")
    get_date_wise_data = fields.Selection([('before', 'Before'), ('after', 'After'), ('today', 'Today'),
                                           ('between', 'Between')])
    state = fields.Selection([('draft', 'Draft'), ('confirm', 'Confirm'), ('done', 'Done')], default='draft')

    def confirm(self):
        """
        This method is used to confirm records.
        @Author: DG
        """
        self.state = 'confirm'

    def action_bulk_confirm_records(self):
        """
        This method is used to bulk unlink attachment records with it's filestore.
        @Author: DG
        """
        if self.filtered(lambda r: r.state == 'done'):
            raise ValidationError('One or many records are already deleted/unlinked.')
        for rec in self:
            rec.confirm()

    def unlink_attachment_with_filestore(self):
        """
        This method is used to unlink attachment records with it's filestore.
        @Author: DG
        """
        confirm_unlink_records = self.search([('state', '=', 'confirm')], limit=200)
        for rec in confirm_unlink_records:
            date_filter = rec.get_date_wise_data
            attachment_obj = self.env['ir.attachment']
            filestore_path = attachment_obj._full_path('')

            if date_filter == 'before':
                search_domain = [('create_date', '<=', rec.before_date), ('mimetype', '=', rec.mime_type),
                                 ('res_model', '=', rec.model_id.model)]
            elif date_filter == 'after':
                search_domain = [('create_date', '>=', rec.after_date), ('mimetype', '=', rec.mime_type),
                                 ('res_model', '=', rec.model_id.model)]
            elif date_filter == 'today':
                search_domain = [('create_date', '<=', rec.only_today_date), ('create_date', '>=', rec.only_today_date),
                                 ('mimetype', '=', rec.mime_type),
                                 ('res_model', '=', rec.model_id.model)]
            elif date_filter == 'between':
                search_domain = [('create_date', '>=', rec.from_date), ('create_date', '<=', rec.to_date),
                                 ('mimetype', '=', rec.mime_type), ('res_model', '=', rec.model_id.model)]

            attachments = attachment_obj.search(search_domain)
            if attachments:
                for attachment in attachments.mapped('store_fname'):
                    if not attachment:
                        continue
                    folder_name = attachment.split('/')
                    filestore_inner_files = os.listdir(os.path.join(filestore_path, folder_name[0]))
                    if folder_name[1] in filestore_inner_files:
                        os.unlink(os.path.join(filestore_path, attachment))

                message_post_body = "At the time of unlink process {} records found, and it's unlinked.".format(
                    len(attachments))
                attachments.unlink()
            else:
                message_post_body = "At the time of unlink process not found any records of attachments."
            rec.state = 'done'
            rec.message_post(body=message_post_body)
