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
    preview_attachment_ids = fields.Many2many(
        'ir.attachment', 'unlink_filestore_preview_attachment_rel',
        'cleanup_id', 'attachment_id', string='Preview Snapshot', copy=False)


    @api.constrains('record_limit')
    def _check_record_limit(self):
        for rec in self:
            if rec.record_limit < 1:
                raise ValidationError('Attachment Limit must be at least 1.')

    def _get_filter_domain(self):
        self.ensure_one()
        if not self.model_id or not self.model_name:
            raise ValidationError('Please select a model.')
        try:
            domain = literal_eval(self.filter_domain or '[]')
        except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError) as exc:
            raise ValidationError('Invalid domain filter: %s' % exc) from exc
        if not isinstance(domain, (list, tuple)):
            raise ValidationError('The domain filter must be a valid Odoo domain list.')
        return list(domain)

    def _get_matching_attachments(self):
        """Return an attachment search domain and model record count.

        When the selected model itself is ir.attachment, search its records
        directly. Otherwise find attachments linked to matching model records.
        """
        self.ensure_one()
        domain = self._get_filter_domain()
        attachment_obj = self.env['ir.attachment']
        target_obj = self.env[self.model_name]
        target_count = target_obj.search_count(domain)

        if self.model_name == 'ir.attachment':
            attachment_domain = domain
        else:
            target_ids = target_obj.search(domain).ids
            attachment_domain = [
                ('res_model', '=', self.model_name),
                ('res_id', 'in', target_ids),
            ]
        if self.mime_type:
            attachment_domain = list(attachment_domain) + [
                ('mimetype', '=', self.mime_type.strip())
            ]
        return target_count, attachment_obj, attachment_domain

    def _check_preview_state(self):
        self.ensure_one()
        if self.state == 'done':
            raise ValidationError('This cleanup has already been completed.')
        if self.record_limit < 1:
            raise ValidationError('Attachment Limit must be at least 1.')

    def _update_preview_counts(self):
        self.ensure_one()
        target_count, attachment_obj, domain = self._get_matching_attachments()
        matching_count = attachment_obj.search_count(domain)
        candidates = attachment_obj.search(domain, order='id asc', limit=self.record_limit)
        self.write({
            'matching_record_count': target_count,
            'matching_attachment_count': matching_count,
            'preview_attachment_count': len(candidates),
            'preview_date': fields.Datetime.now(),
            'preview_attachment_ids': [(6, 0, candidates.ids)],
        })
        return candidates

    def action_preview_records(self):
        """Display matching records from the chosen model, regardless of MIME type."""
        self._check_preview_state()
        domain = self._get_filter_domain()
        target_model = self.env[self.model_name]
        records = target_model.search(domain, order='id asc', limit=self.record_limit)
        self._update_preview_counts()
        return {
            'name': 'Matching Model Records (Preview Only)',
            'type': 'ir.actions.act_window',
            'res_model': self.model_name,
            'view_mode': 'list,form',
            'domain': [('id', 'in', records.ids)],
            'context': {'create': False, 'edit': False, 'delete': False},
            'target': 'current',
        }

    def action_preview_attachments(self):
        """Open limited attachment candidates that the cleanup would unlink."""
        self._check_preview_state()
        candidates = self._update_preview_counts()
        return {
            'name': 'Attachments Selected for Cleanup (Preview Only)',
            'type': 'ir.actions.act_window',
            'res_model': 'ir.attachment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', candidates.ids)],
            'context': {
                'create': False, 'edit': False, 'delete': False,
                'cleanup_preview_job_id': self.id,
            },
            'target': 'current',
        }

    @api.model
    def action_open_manual_delete_wizard(self, attachments):
        """Called by the ir.attachment Action menu with selected list rows."""
        if not self.env.user.has_group('base.group_system'):
            raise ValidationError('Only Settings administrators can manually delete attachments.')
        job_id = self.env.context.get('cleanup_preview_job_id')
        job = self.browse(job_id).exists() if isinstance(job_id, int) else self.browse()
        if not job or job.state == 'done':
            raise ValidationError('Open the attachment list using Preview Attachments to Delete first.')
        if not attachments or len(attachments) > job.record_limit:
            raise ValidationError('Select between 1 and %s attachment(s).' % job.record_limit)
        if not set(attachments.ids).issubset(set(job.preview_attachment_ids.ids)):
            raise ValidationError('Some selected attachments are not in the latest preview. Preview again.')
        wizard = self.env['unlink.attachment.manual.delete'].create({
            'cleanup_id': job.id,
            'attachment_ids': [(6, 0, attachments.ids)],
        })
        return {
            'name': 'Confirm Manual Attachment Deletion',
            'type': 'ir.actions.act_window',
            'res_model': 'unlink.attachment.manual.delete',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
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
            target_count, attachment_obj, search_domain = rec._get_matching_attachments()
            total_before = attachment_obj.search_count(search_domain)
            attachments = attachment_obj.search(search_domain, order='id asc', limit=rec.record_limit)
            count = len(attachments)
            attachments.unlink()
            rec.write({
                'state': 'done',
                'matching_record_count': target_count,
                'matching_attachment_count': total_before,
                'preview_attachment_count': count,
            })
            rec.message_post(body=(
                f'Attachment cleanup completed. {count} matching attachment(s) removed '
                f'(configured limit: {rec.record_limit}).'))


class UnlinkAttachmentManualDelete(models.TransientModel):
    _name = 'unlink.attachment.manual.delete'
    _description = 'Confirm Selected Attachment Deletion'

    cleanup_id = fields.Many2one('unlink.filestore', required=True, readonly=True)
    attachment_ids = fields.Many2many('ir.attachment', string='Selected Attachments', readonly=True)
    selected_count = fields.Integer(compute='_compute_selected_count')

    @api.depends('attachment_ids')
    def _compute_selected_count(self):
        for wizard in self:
            wizard.selected_count = len(wizard.attachment_ids)

    def action_confirm_delete(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise ValidationError('Only Settings administrators can manually delete attachments.')
        job = self.cleanup_id.exists()
        if not job or job.state == 'done':
            raise ValidationError('This cleanup configuration is no longer available.')
        attachments = self.attachment_ids.exists()
        if not attachments or len(attachments) > job.record_limit:
            raise ValidationError('Selected attachments exceed the configured limit or no longer exist.')
        if not set(attachments.ids).issubset(set(job.preview_attachment_ids.ids)):
            raise ValidationError('Preview changed. Open a new preview and select attachments again.')
        # Recheck against CURRENT domain, MIME type and linked model records.
        _, attachment_obj, matching_domain = job._get_matching_attachments()
        from odoo.osv import expression
        still_matching = attachment_obj.search(expression.AND([
            matching_domain, [('id', 'in', attachments.ids)]
        ])).ids
        if set(still_matching) != set(attachments.ids):
            raise ValidationError('Some attachments no longer match the filter. Preview again.')
        count = len(attachments)
        # Administrators explicitly confirm deletion. Let Odoo handle filestore GC.
        attachments.sudo().unlink()
        job.message_post(body='%s attachment(s) manually deleted from the preview by %s.' % (
            count, self.env.user.display_name))
        job._update_preview_counts()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'unlink.filestore',
            'res_id': job.id, 'view_mode': 'form', 'target': 'current',
        }
