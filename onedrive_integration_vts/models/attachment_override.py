# -*- coding: utf-8 -*-
"""
ir.attachment override — OneDrive Folder Mapping Engine hook
=============================================================
When a new attachment is saved with file content (datas) on a record whose
model matches an active onedrive.folder.rule, we automatically upload the file
to the configured OneDrive folder and create a corresponding documents.document.

Design notes:
  • We only act when datas (binary content) is present — URL-only or empty
    attachments are silently skipped.
  • Errors in the upload path are caught and logged; they never cause the
    original attachment creation to fail.
  • We build a model→rules lookup once per create call for efficiency.
  • A table_exists() guard prevents crashes on the first load before the
    module has been upgraded (the table may not exist in the DB yet).
"""
import logging

from odoo import api, models , fields
from odoo.tools import sql as odoo_sql
# from orm import fields

_logger = logging.getLogger(__name__)


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    onedrive_synced = fields.Boolean(string="Uploaded to OneDrive", default=False,copy=False, index=True )
    onedrive_sync_failed = fields.Boolean(string="OneDrive Upload Failed", default=False, copy=False, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        """
        Create attachments normally, then attempt OneDrive upload for any that:
          1. Have binary content (datas field is set)
          2. Are linked to a record (res_model + res_id both set)
          3. Match at least one active onedrive.folder.rule
        """
        attachments = super().create(vals_list)

        # ── Safety guard ────────────────────────────────────────────────────
        # This override runs on EVERY ir.attachment creation system-wide,
        # including internal Odoo operations (asset bundles, mail attachments,
        # etc.). If the module has been added to __init__.py but the DB table
        # hasn't been created yet (i.e., the module hasn't been upgraded),
        # querying onedrive_folder_rule would raise ProgrammingError.
        # We check for table existence first to avoid crashing Odoo on startup.
        if not odoo_sql.table_exists(self.env.cr, "onedrive_folder_rule"):
            return attachments

        # Fast exit: skip if no active rules exist (avoids repeated DB load on
        # every attachment creation when the feature is not configured)
        Rule = self.env["onedrive.folder.rule"]
        rules = Rule.search([("active", "=", True)])
        if not rules:
            return attachments

        # Index rules by technical model name for O(1) lookups
        rules_by_model = {}
        for rule in rules:
            if rule.model_name:
                rules_by_model.setdefault(rule.model_name, []).append(rule)

        # Process each newly created attachment
        for attachment in attachments:
            # Only process attachments that have binary content AND a linked record
            if not attachment.file_size or not attachment.res_model or not attachment.res_id or attachment.onedrive_synced:
                continue

            matching_rules = rules_by_model.get(attachment.res_model, [])
            if not matching_rules:
                continue
            uploaded = False
            for rule in matching_rules:
                try:
                    res = rule.process_attachment(attachment)
                    if res:
                        uploaded = True
                        self.env["onedrive.sync.history"].create_log(
                            operation="upload",
                            status="success",
                            message=f"Uploaded '{attachment.name}' to OneDrive via rule '{rule.name}'.",
                            config_id=rule.onedrive_config_id.id,
                            file_name=attachment.name,
                            onedrive_item_id=res if isinstance(res, str) else False,
                            res_model=attachment.res_model,
                            res_id=attachment.res_id,
                        )
                    else:
                        self.env["onedrive.sync.history"].create_log(
                            operation="upload",
                            status="failed",
                            message=f"Upload returned no result for '{attachment.name}'. Check server logs for details.",
                            config_id=rule.onedrive_config_id.id,
                            file_name=attachment.name,
                            res_model=attachment.res_model,
                            res_id=attachment.res_id,
                        )
                except Exception as e:
                    self.env["onedrive.sync.history"].create_log(
                        operation="upload",
                        status="failed",
                        message=f"Exception during upload of '{attachment.name}': {str(e)}",
                        config_id=rule.onedrive_config_id.id,
                        file_name=attachment.name,
                        res_model=attachment.res_model,
                        res_id=attachment.res_id,
                    )
                    _logger.exception(
                        "[OneDrive Rule '%s'] Unexpected error while processing "
                        "attachment '%s' (id=%s). The file was saved locally.",
                        rule.name,
                        attachment.name,
                        attachment.id,
                    )
            if uploaded:
                attachment.sudo().write({"onedrive_synced": True})

        return attachments

    def unlink(self):
        """
        When an attachment is deleted from Odoo, check if it was synced to OneDrive.
        If it was, and the configuration has auto_delete enabled, remove it from OneDrive too.
        """
        if not odoo_sql.table_exists(self.env.cr, "documents_document") or \
           not odoo_sql.table_exists(self.env.cr, "onedrive_folder_rule"):
            return super().unlink()

        Document = self.env["documents.document"].sudo()
        docs_to_delete_from_onedrive = Document
        
        for attachment in self:
            if not attachment.res_model or not attachment.res_id:
                continue

            # Check by attachment_id first
            matching_docs = Document.search([
                ("attachment_id", "=", attachment.id),
                ("onedrive_id", "!=", False)
            ])
            
            # Fall back to matching by model, id, and name
            if not matching_docs:
                matching_docs = Document.search([
                    ("res_model", "=", attachment.res_model),
                    ("res_id", "=", attachment.res_id),
                    ("name", "=", attachment.name),
                    ("onedrive_id", "!=", False)
                ])
                
            docs_to_delete_from_onedrive |= matching_docs

        for doc in docs_to_delete_from_onedrive:
            try:
                config = doc.onedrive_config_id
                if config and config.state == "connected" and config.auto_delete:
                    doc.delete_from_onedrive()
                    self.env["onedrive.sync.history"].create_log(
                        operation="delete",
                        status="success",
                        message=f"'{doc.name}' deleted from OneDrive (auto-delete on attachment unlink).",
                        config_id=config.id,
                        file_name=doc.name,
                        onedrive_item_id=doc.onedrive_id or False,
                        res_model=doc.res_model,
                        res_id=doc.res_id,
                    )
            except Exception as e:
                if doc.onedrive_config_id:
                    self.env["onedrive.sync.history"].create_log(
                        operation="delete",
                        status="failed",
                        message=f"Auto-delete failed for '{doc.name}': {str(e)}",
                        config_id=doc.onedrive_config_id.id,
                        file_name=doc.name,
                        onedrive_item_id=doc.onedrive_id or False,
                        res_model=doc.res_model,
                        res_id=doc.res_id,
                    )
                _logger.warning(
                    "[OneDrive Rule] Auto-delete failed for document '%s' (id=%s): %s",
                    doc.name, doc.id, str(e)
                )

        res = super().unlink()

        # Clean up the corresponding documents.document records from Odoo
        # if they weren't already cascade-deleted by super().unlink()
        existing_docs = docs_to_delete_from_onedrive.exists()
        if existing_docs:
            try:
                existing_docs.with_context(no_onedrive_sync=True).unlink()
            except Exception as e:
                _logger.warning("[OneDrive Rule] Could not delete local document proxy: %s", str(e))

        return res

    def action_upload_to_onedrive(self):
        """Upload the selected attachments to OneDrive using their folder mapping rule."""
        Rule = self.env["onedrive.folder.rule"].sudo()
        History = self.env["onedrive.sync.history"]
        done = skipped = failed = 0

        for attachment in self.sudo():
            # already uploaded, no content, or not linked to a record -> skip
            if (attachment.onedrive_synced or not attachment.file_size
                    or not attachment.res_model or not attachment.res_id):
                skipped += 1
                continue

            rule = Rule.search([
                ("active", "=", True),
                ("model_name", "=", attachment.res_model),
            ], limit=1)
            if not rule:
                skipped += 1
                continue

            try:
                with self.env.cr.savepoint():
                    result = rule.process_attachment(attachment)
                    if result:
                        attachment.write({"onedrive_synced": True})
                if result:
                    done += 1
                    History.create_log(
                        operation="upload", status="success",
                        message=f"'{attachment.name}' uploaded to OneDrive manually via rule '{rule.name}'.",
                        config_id=rule.onedrive_config_id.id,
                        file_name=attachment.name, onedrive_item_id=result,
                        res_model=attachment.res_model, res_id=attachment.res_id,
                    )
                else:
                    failed += 1
                    History.create_log(
                        operation="upload", status="failed",
                        message=f"'{attachment.name}' was not uploaded",
                        config_id=rule.onedrive_config_id.id,
                        file_name=attachment.name,
                        res_model=attachment.res_model, res_id=attachment.res_id,
                    )
            except Exception as e:
                failed += 1
                _logger.exception("[OneDrive] Manual upload failed for attachment %s", attachment.id)
                History.create_log(
                    operation="upload", status="failed",
                    message=f"Failed to upload '{attachment.name}': {e}",
                    config_id=rule.onedrive_config_id.id,
                    file_name=attachment.name,
                    res_model=attachment.res_model, res_id=attachment.res_id,
                )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Upload to OneDrive",
                "message": f"Uploaded: {done}, skipped (already synced / no rule / no file): {skipped}, failed: {failed}.",
                "type": "success" if not failed else "warning",
                "sticky": bool(failed),
            },
        }

