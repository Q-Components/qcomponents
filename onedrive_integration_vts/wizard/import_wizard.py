# -*- coding: utf-8 -*-
from odoo import models, fields
from odoo.exceptions import UserError


class OneDriveImportWizard(models.TransientModel):
    _name = "onedrive.import.wizard"
    _description = "OneDrive Import Wizard"

    onedrive_config_id = fields.Many2one(
        "onedrive.configuration",
        string="OneDrive Connection",
    )
    import_scope = fields.Selection([
        ("root", "Root Items Only"),
        ("all", "Root Items + All Child Items"),
    ], default="root", string="Import Scope")

    max_upload_size_mb = fields.Char(
        compute="compute_max_upload_size_mb"
    )

    def compute_max_upload_size_mb(self):

        max_size = int(
            self.env["ir.config_parameter"].sudo().get_param(
                "document.max_fileupload_size",
                67000000
            )
        )

        for rec in self:
            rec.max_upload_size_mb = str(round(max_size / 1000000, 2))

    def action_import_files(self):
        self.ensure_one()

        config = self.onedrive_config_id
        if not config:
            raise UserError("Please select an OneDrive connection before importing.")

        # ── Auto-refresh access token before every import ─────────────────────
        # Tokens can expire silently between sessions. Refreshing here ensures
        # the Graph API calls in import_onedrive() always use a valid token,
        # avoiding cryptic 401 errors mid-import.
        config.refresh_onedrive_access_token()

        if not config.ms_access_token:
            raise UserError(
                "Could not obtain a valid OneDrive access token. "
                "Please reconnect your OneDrive account from the configuration."
            )

        return self.env["documents.document"].import_onedrive(
            config,
            recursive=self.import_scope == "all"
        )
