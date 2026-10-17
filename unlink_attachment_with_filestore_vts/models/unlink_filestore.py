from ast import literal_eval

from odoo import api, models, fields
from odoo.exceptions import ValidationError


class UnlinkFilestore(models.Model):
    _name = 'unlink.filestore'
    _description = "Unlink Filestore"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'analytic.mixin']
    _rec_name = 'model_id'

    model_id = fields.Many2one(comodel_name='ir.model', string="Model Name")
    model_name = fields.Char(related='model_id.model', string='Technical Model', readonly=True)
    filter_domain = fields.Char(string='Domain Filter', default='[]',
                                help='Filter records of the selected model before deleting their attachments.')

    @api.onchange('model_id')
    def _onchange_model_id_reset_domain(self):
        self.filter_domain = '[]'

    record_limit = fields.Integer(
        string='Attachment Limit', default=100,
        help='Maximum number of matching attachments to delete in one run. Must be greater than zero.')
    matching_record_count = fields.Integer(string='Matching Model Records', readonly=True, copy=False)
    matching_attachment_count = fields.Integer(string='Matching Attachments', readonly=True, copy=False)
    preview_attachment_count = fields.Integer(string='Attachments Within Limit', readonly=True, copy=False)
    preview_date = fields.Datetime(string='Last Preview', readonly=True, copy=False)

    @api.constrains('record_limit')
    def _check_record_limit(self):
        for rec in self:
            if rec.record_limit < 1:
                raise ValidationError('Attachment Limit must be at least 1.')

    def _get_matching_attachments(self, limit=None):
        """Return matching attachments using exactly the cleanup filters."""
        self.ensure_one()
        if not self.model_id or not self.model_name:
            raise ValidationError('Please select a model.')
        try:
            domain = literal_eval(self.filter_domain or '[]')
        except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError) as exc:
            raise ValidationError('Invalid domain filter: %s' % exc) from exc
        if not isinstance(domain, (list, tuple)):
            raise ValidationError('The domain filter must be a valid Odoo domain list.')
        target = self.env[self.model_name].search(domain)
        attachment_domain = [('res_model', '=', self.model_name), ('res_id', 'in', target.ids)]
        if self.mime_type:
            attachment_domain.append(('mimetype', '=', self.mime_type))
        attachments = self.env['ir.attachment']
        return target, attachments, attachment_domain

    def action_preview_attachments(self):
        """Show exactly the attachment rows eligible for the next limited cleanup."""
        self.ensure_one()
        if self.state == 'done':
            raise ValidationError('This cleanup has already been completed.')
        if self.record_limit < 1:
            raise ValidationError('Attachment Limit must be at least 1.')
        target, attachment_obj, domain = self._get_matching_attachments()
        matching_count = attachment_obj.search_count(domain)
        candidates = attachment_obj.search(domain, order='id asc', limit=self.record_limit)
        self.write({
            'matching_record_count': len(target),
            'matching_attachment_count': matching_count,
            'preview_attachment_count': len(candidates),
            'preview_date': fields.Datetime.now(),
        })
        return {
            'name': 'Attachments Selected for Cleanup (Preview Only)',
            'type': 'ir.actions.act_window',
            'res_model': 'ir.attachment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', candidates.ids)],
            'context': {'create': False, 'edit': False, 'delete': False},
            'target': 'current',
        }

    mime_type = fields.Char(string="Mime Type", help="Set file format.")
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
        """Remove only attachments matching the selected model and record domain.

        Odoo's ir.attachment.unlink() handles associated filestore cleanup; removing
        files directly first could break a file shared by other attachments.
        """
        jobs = self.search([('state', '=', 'confirm')], limit=200)
        attachment_obj = self.env['ir.attachment']
        for rec in jobs:
            if not rec.model_id or not rec.model_name:
                raise ValidationError('Please select a model before confirming cleanup.')

            if rec.record_limit < 1:
                raise ValidationError('Attachment Limit must be at least 1.')
            target, attachment_obj, search_domain = rec._get_matching_attachments()
            total_before = attachment_obj.search_count(search_domain)
            attachments = attachment_obj.search(search_domain, order='id asc', limit=rec.record_limit)
            count = len(attachments)
            attachments.unlink()
            rec.write({
                'state': 'done',
                'matching_record_count': len(target),
                'matching_attachment_count': total_before,
                'preview_attachment_count': count,
            })
            rec.message_post(body=(
                f'Attachment cleanup completed. {count} matching attachment(s) removed '
                f'(configured limit: {rec.record_limit}).'))
