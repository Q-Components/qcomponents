# -*- coding: utf-8 -*-
"""
OneDrive Sync History
======================
Tracks every operation performed by the OneDrive integration:
  - upload    : Attachment uploaded to OneDrive from an Odoo record
  - download  : File imported from OneDrive into Odoo
  - delete    : File deleted from OneDrive (auto-delete)
  - webhook   : Delta sync triggered by a Microsoft Graph webhook
  - folder    : Folder created in OneDrive
"""
import logging as _logging
from odoo import api, fields, models

_hist_logger = _logging.getLogger(__name__)


class OneDriveSyncHistory(models.Model):
    _name        = "onedrive.sync.history"
    _description = "OneDrive Synchronization History"
    _order       = "create_date desc, id desc"
    _log_access  = True   # keep create_date / write_date

    # ── Who / What ─────────────────────────────────────────────────────────────
    config_id = fields.Many2one(
        "onedrive.configuration",
        string="OneDrive Config",
        ondelete="set null",
        index=True,
    )
    operation = fields.Selection([
        ("upload",   "Upload to OneDrive"),
        ("download", "Import to Odoo"),
        ("update", "Update to OneDrive"),
        ("delete",   "Delete from OneDrive"),
        ("webhook",  "Webhook / Delta Sync"),
        ("folder",   "Folder Created"),
        ("restore","Restore from OneDrive"),
    ], string="Operation", required=True, index=True)

    # ── Result ─────────────────────────────────────────────────────────────────
    status = fields.Selection([
        ("success", "Success"),
        ("failed",  "Failed"),
        ("skipped", "Skipped"),
    ], string="Status", required=True, index=True)
    message = fields.Text(string="Log Message")

    # ── File / Record context ──────────────────────────────────────────────────
    file_name        = fields.Char(string="File / Folder Name")
    onedrive_item_id = fields.Char(string="OneDrive Item ID")
    folder_path      = fields.Char(
        string="OneDrive Path",
        help="Slash-separated path inside OneDrive, e.g. 2026 / May / S00026",
    )
    res_model = fields.Char(string="Odoo Model")
    res_id    = fields.Integer(string="Record ID")

    # ── Convenience display ────────────────────────────────────────────────────
    record_display = fields.Char(
        string="Record",
        compute="_compute_record_display",
        store=False,
    )

    @api.depends("res_model", "res_id")
    def _compute_record_display(self):
        for rec in self:
            if rec.res_model and rec.res_id:
                try:
                    obj = self.env[rec.res_model].sudo().browse(rec.res_id)
                    rec.record_display = obj.display_name if obj.exists() else f"{rec.res_model}({rec.res_id})"
                except Exception:
                    rec.record_display = f"{rec.res_model}({rec.res_id})"
            else:
                rec.record_display = False

    # ── Cron: clean up old logs ────────────────────────────────────────────────
    @api.model
    def _cron_cleanup_old_logs(self, days=90):
        """Delete sync history logs older than *days* days (default 90)."""
        cutoff = fields.Datetime.subtract(fields.Datetime.now(), days=days)
        old = self.search([("create_date", "<", cutoff)])
        count = len(old)
        old.unlink()
        _hist_logger.info(
            "[OneDrive History] Cleaned up %d log(s) older than %d days.", count, days
        )

    # ── Core helper ────────────────────────────────────────────────────────────
    @api.model
    def create_log(
        self,
        operation,
        status,
        message,
        config_id=False,
        file_name=False,
        onedrive_item_id=False,
        folder_path=False,
        res_model=False,
        res_id=False,
    ):
        """
        Safe, reusable helper to write a sync history record.

        Uses a database SAVEPOINT so that a failure here NEVER rolls back
        the caller's transaction.  Runs under sudo() so ACL rules never
        block the logging.

        Parameters
        ----------
        operation        : str  — upload / download / delete / webhook / folder
        status           : str  — success / failed / skipped
        message          : str  — Human-readable description of what happened.
        config_id        : int or onedrive.configuration recordset (optional)
        file_name        : str  — Name of the file or folder.
        onedrive_item_id : str  — Microsoft Graph item ID.
        folder_path      : str  — Slash-separated path (e.g. "2026 / May / S00026").
        res_model        : str  — Technical Odoo model name (e.g. 'sale.order').
        res_id           : int  — ID of the Odoo record.
        """
        try:
            # Resolve config_id to plain int
            if config_id and not isinstance(config_id, int):
                config_id = config_id.id if config_id else False

            self.env.cr.execute("SAVEPOINT onedrive_history_log")
            self.sudo().create({
                "config_id":        config_id or False,
                "operation":        operation,
                "status":           status,
                "message":          str(message) if message else "",
                "file_name":        file_name or False,
                "onedrive_item_id": onedrive_item_id or False,
                "folder_path":      folder_path or False,
                "res_model":        res_model or False,
                "res_id":           int(res_id) if res_id else False,
            })
            self.env.cr.execute("RELEASE SAVEPOINT onedrive_history_log")

        except Exception as exc:
            try:
                self.env.cr.execute("ROLLBACK TO SAVEPOINT onedrive_history_log")
            except Exception:
                pass
            _hist_logger.error(
                "[OneDrive History] Failed to write log "
                "(op=%s status=%s file=%s): %s",
                operation, status, file_name, exc,
            )
