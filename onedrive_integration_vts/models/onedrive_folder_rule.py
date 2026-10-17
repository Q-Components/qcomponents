# -*- coding: utf-8 -*-
"""
OneDrive Folder Mapping Rule
==============================
Each rule associates an Odoo model (e.g. sale.order) with a specific folder
in OneDrive.  When a file is attached to any record of that model, this engine
automatically:

  1. Creates a subfolder in OneDrive named after the record (configurable pattern).
  2. Uploads the file into that subfolder.
  3. Creates a matching documents.document record so the file is visible in the
     Odoo Documents sidebar under its OneDrive folder.

Graph API endpoints used:
  GET  /me/drive/items/{folder_id}/children          – list children
  POST /me/drive/items/{folder_id}/children          – create folder
  PUT  /me/drive/items/{folder_id}:/{filename}:/content  – simple upload (<= 4 MB)
  POST /me/drive/items/{folder_id}:/{filename}:/createUploadSession  – large-file session
"""
import base64
import json
import logging
import requests
import urllib.parse
import string
from odoo import _, api, fields, models
from odoo.exceptions import UserError , ValidationError

_logger = logging.getLogger(__name__)

# Microsoft Graph base URL for the current user's drive
GRAPH_DRIVE_URL = "https://graph.microsoft.com/v1.0/me/drive"

# Files above this size (bytes) use the chunked upload-session API
LARGE_FILE_THRESHOLD = 4 * 1024 * 1024   # 4 MB
CHUNK_SIZE           = 5 * 1024 * 1024   # 5 MB per chunk

# Characters disallowed by OneDrive in file/folder names
INVALID_CHARS = r'\/:*?"<>|'


class OneDriveFolderRule(models.Model):
    _name        = "onedrive.folder.rule"
    _description = "OneDrive Folder Mapping Rule"
    _order       = "sequence, id"

    # ── Basic ─────────────────────────────────────────────────────────────────
    name     = fields.Char(string="Rule Name", required=True, translate=True)
    active   = fields.Boolean(string="Active", default=True)
    sequence = fields.Integer(string="Sequence", default=10)

    # ── OneDrive connection ───────────────────────────────────────────────────
    onedrive_config_id = fields.Many2one(
        "onedrive.configuration",
        string="OneDrive Configuration",
        required=True,
        ondelete="cascade",
        index=True,
        help="Which connected OneDrive account to use for this rule.",
    )

    # ── Odoo source model ─────────────────────────────────────────────────────
    model_id = fields.Many2one(
        "ir.model",
        string="Odoo Model",
        required=True,
        ondelete="cascade",
        index=True,
        help="Files attached to records of this model will be uploaded to OneDrive.",
    )
    # Stored so we can index/search without joining to ir.model every time
    model_name = fields.Char(
        string="Technical Model Name",
        related="model_id.model",
        store=True,
        readonly=True,
        index=True,
    )

    # ── OneDrive target folder ────────────────────────────────────────────────
    onedrive_folder_id = fields.Char(
        string="Target OneDrive Folder ID",
        help=(
            "Paste the OneDrive item ID of the parent folder where record subfolders "
            "will be created.  Use the 'Verify Folder' button to confirm the ID is valid."
        ),
    )
    onedrive_folder_name = fields.Char(
        string="Target Folder Name",
        readonly=True,
        help="Auto-filled by 'Verify Folder'.  Shows the actual name of the OneDrive folder.",
    )

    # ── Subfolder naming pattern ──────────────────────────────────────────────
    subfolder_pattern = fields.Char(
        string="Subfolder Pattern",
        required=True,
        default="{name}",
        help=(
            "Python str.format() template to name the per-record subfolder.\n"
            "Placeholders: any field name on the model, e.g.\n"
            "  {name}           → the record's display name\n"
            "  {id}-{name}      → 42-My Sale Order\n"
            "  SO-{name}        → SO-My Sale Order"
        ),
    )

    # ── Date-based folder hierarchy ───────────────────────────────────────────
    create_year_folder = fields.Boolean(
        string="Create Year Folder",
        default=False,
        help=(
            "If enabled, a folder named after the record's creation year "
            "(e.g. '2026') will be created inside the target OneDrive folder, "
            "and all subfolders will be placed inside it."
        ),
    )
    create_month_folder = fields.Boolean(
        string="Create Month Folder",
        default=False,
        help=(
            "If enabled, a folder named after the record's creation month "
            "(e.g. 'May') will be created inside the Year folder (if enabled) "
            "or directly inside the target folder. "
            "Requires 'Create Year Folder' to be meaningful but works independently."
        ),
    )

    # ── Stats (computed) ──────────────────────────────────────────────────────
    upload_count = fields.Integer(
        string="Files Uploaded",
        compute="_compute_upload_count",
        help="Number of documents.document records linked to this rule.",
    )

    sync_existing_attachments = fields.Boolean(
        string="Sync Existing Attachments",
        default=False,
        help="Upload attachments that existed before this rule was configured.",
    )


    @api.constrains("model_id", "active")
    def _check_one_rule_per_model(self):
        """Only one active folder mapping rule is allowed per Odoo model."""
        for rule in self.filtered("active"):
            duplicate = self.search([
                ("id", "!=", rule.id),
                ("model_id", "=", rule.model_id.id),
                ("active", "=", True),
            ], limit=1)
            if duplicate:
                raise ValidationError(_(
                    "A folder mapping rule already exists for model '%(model)s' (rule: '%(rule)s'). "
                    "Only one active rule is allowed per model. Edit the existing rule, "
                    "or archive it first.",
                    model=rule.model_id.name, rule=duplicate.name,
                ))

    def upload_existing_attachments(self):
        """
        Cron job: upload ALL existing attachments (onedrive_synced=False)
        of every rule that has 'Sync Existing Attachments' enabled.
        Commits after every 30 attachments.
        """
        Attachment = self.env["ir.attachment"].sudo()

        rules = self.search([
            ("active", "=", True),
            ("sync_existing_attachments", "=", True),
        ])

        for rule in rules:
            # Skip a rule that cannot work (checked once, not for every file)
            if (
                    rule.onedrive_config_id.state != "connected"
                    or not rule.onedrive_folder_id
                    or not rule.model_name
            ):
                _logger.warning(
                    "[OneDrive] Rule '%s' skipped: config not connected, "
                    "folder not set or model not installed.", rule.name,
                )
                continue

            Model = self.env[rule.model_name]
            attachments = Attachment.search([
                ("res_model", "=", rule.model_name),
                ("res_id", ">", 0),
                ("onedrive_synced", "=", False),
            ], order="id",limit=120)

            processed = 0
            for attachment in attachments:
                try:
                    if attachment.datas and Model.browse(attachment.res_id).exists():
                        with self.env.cr.savepoint():
                            result = rule.process_attachment(attachment)
                            if result:
                                attachment.write({"onedrive_synced": True})

                        if result:
                            self.env["onedrive.sync.history"].create_log(
                                operation="upload",
                                status="success",
                                message=(
                                    f"Existing attachment '{attachment.name}' "
                                    f"uploaded to OneDrive via rule '{rule.name}'."
                                ),
                                config_id=rule.onedrive_config_id.id,
                                file_name=attachment.name,
                                onedrive_item_id=result,
                                res_model=attachment.res_model,
                                res_id=attachment.res_id,
                            )
                        else:
                            self.env["onedrive.sync.history"].create_log(
                                operation="upload",
                                status="failed",
                                message=(
                                    f"Existing attachment '{attachment.name}' was not uploaded "
                                    f"(no result). Check the server logs for the reason."
                                ),
                                config_id=rule.onedrive_config_id.id,
                                file_name=attachment.name,
                                res_model=attachment.res_model,
                                res_id=attachment.res_id,
                            )
                except Exception as e:
                    _logger.exception(
                        "[OneDrive] Failed to upload existing attachment '%s' (ID %s): %s",
                        attachment.name, attachment.id, e,
                    )
                    try:
                        with self.env.cr.savepoint():
                            self.env["onedrive.sync.history"].create_log(
                                operation="upload",
                                status="failed",
                                message=f"Failed to upload existing attachment '{attachment.name}': {e}",
                                config_id=rule.onedrive_config_id.id,
                                file_name=attachment.name,
                                res_model=attachment.res_model,
                                res_id=attachment.res_id,
                            )
                    except Exception:
                        _logger.exception("[OneDrive] Could not write sync history log.")

                processed += 1
                if processed % 30 == 0:
                    self.env.cr.commit()
                    self.env.invalidate_all()



    def _compute_upload_count(self):
        # Count documents where the onedrive_config points to our config and
        # the res_model matches.  Lightweight proxy metric.
        for rule in self:
            rule.upload_count = self.env["documents.document"].search_count([
                ("onedrive_config_id", "=", rule.onedrive_config_id.id),
                ("res_model", "=", rule.model_name),
            ])

    # ──────────────────────────────────────────────────────────────────────────
    # UI Actions
    # ──────────────────────────────────────────────────────────────────────────

    def action_verify_folder(self):
        """
        Call the Graph API to confirm the folder ID is valid and store its name.
        Displays a success notification with the resolved folder name.
        """
        self.ensure_one()
        config = self.onedrive_config_id
        token = self._get_fresh_token(config)
        if not token:
            raise UserError(_("No valid access token.  Please reconnect OneDrive."))

        url = f"{GRAPH_DRIVE_URL}/items/{self.onedrive_folder_id}"
        try:
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
        except requests.exceptions.RequestException as exc:
            raise UserError(_("Network error: %s") % exc) from exc

        if resp.status_code == 200:
            folder_name = resp.json().get("name", "Unknown")
            self.onedrive_folder_name = folder_name
            return self._display_notification(
                message=_("Folder verified: '%s'") % folder_name,
                title=_("Success"),
                msg_type="success",
            )
        else:
            raise UserError(
                _("Could not reach the OneDrive folder (HTTP %s):\n%s")
                % (resp.status_code, resp.text)
            )

    def action_open_folder_picker(self):
        """
        Opens the OneDrive Folder Picker wizard to visually browse and select a folder.
        """
        self.ensure_one()
        if not self.onedrive_config_id:
            raise UserError(_("Please select a OneDrive Configuration first."))
            
        wizard = self.env["onedrive.folder.picker"].create({
            "config_id": self.onedrive_config_id.id,
            "rule_id": self.id,
        })
        wizard._fetch_folders("root")
        
        return wizard._reopen_wizard()

    # ──────────────────────────────────────────────────────────────────────────
    # Core Processing  (called by the ir.attachment override)
    # ──────────────────────────────────────────────────────────────────────────

    def process_attachment(self, attachment):
        """
        Upload *attachment* to the correct OneDrive subfolder and create a
        matching documents.document record.

        :param attachment: ir.attachment recordset (single)
        :returns:          OneDrive item ID (str) on success, or None.
        """
        self.ensure_one()

        config = self.onedrive_config_id

        # Guard: config must be connected
        if config.state != "connected":
            _logger.warning(
                "[OneDrive Rule '%s'] Config '%s' is not connected – skipping upload.",
                self.name, config.name,
            )
            return None

        # Guard: attachment must have file content
        if not attachment.datas:
            _logger.debug(
                "[OneDrive Rule '%s'] Attachment '%s' has no binary content – skipping.",
                self.name, attachment.name,
            )
            return None

        # Look up the source Odoo record
        record = self.env[self.model_name].browse(attachment.res_id)
        if not record.exists():
            _logger.warning(
                "[OneDrive Rule '%s'] Source record %s(%s) not found – skipping.",
                self.name, self.model_name, attachment.res_id,
            )
            return None

        token = self._get_fresh_token(config)
        if not token:
            _logger.warning("[OneDrive Rule '%s'] No valid access token – skipping.", self.name)
            return None

        # 1. Determine the effective parent folder for the record subfolder.
        #    If year/month folders are enabled, create them first under the
        #    configured target folder and use the deepest one as parent.
        effective_parent_id = self._resolve_date_parent_folder(
            token, self.onedrive_folder_id, record
        )
        if not effective_parent_id:
            _logger.error(
                "[OneDrive Rule '%s'] Could not resolve date-based parent folder – aborting.",
                self.name,
            )
            return None

        # 2. Determine / create the per-record subfolder under the effective parent
        subfolder_name = self._get_subfolder_name(record)
        subfolder_id   = self._ensure_onedrive_subfolder(token, effective_parent_id, subfolder_name)
        if not subfolder_id:
            _logger.error(
                "[OneDrive Rule '%s'] Could not create subfolder '%s' – aborting.",
                self.name, subfolder_name,
            )
            return None

        # 3. Upload the file to OneDrive
        onedrive_item_id = self._upload_file_to_onedrive(
            token, subfolder_id, attachment.name, attachment.datas
        )
        if not onedrive_item_id:
            return None

        # 4. Create a documents.document so the file shows up in the sidebar
        self._ensure_document_record(
            config, attachment, onedrive_item_id, subfolder_id, subfolder_name
        )

        _logger.info(
            "[OneDrive Rule '%s'] Uploaded '%s' from %s(%s) → OneDrive folder '%s'.",
            self.name, attachment.name, self.model_name, record.id, subfolder_name,
        )
        return onedrive_item_id

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _get_fresh_token(self, config):
        """Refresh and return a clean (no 'Bearer ' prefix) access token."""
        token = config.sudo().ms_access_token or ""
        if token.startswith("Bearer "):
            token = token[len("Bearer "):]
        return token.strip() or None

    def _resolve_date_parent_folder(self, access_token, root_folder_id, record):
        """
        Resolve the effective parent folder ID based on the Year/Month folder
        settings.  Creates intermediate Year and/or Month folders in OneDrive
        as needed, then returns the ID of the deepest resolved folder.

        Folder hierarchy built (depending on flags):
          <Target Folder>
            └── <Year>          (only when create_year_folder=True)
                  └── <Month>   (only when create_month_folder=True)

        :param root_folder_id: OneDrive item ID of the configured target folder.
        :param record:         The Odoo source record (used to read create_date).
        :returns:              OneDrive item ID of the deepest parent folder.
        """
        # If neither date folder option is enabled, return the root as-is.
        if not self.create_year_folder and not self.create_month_folder:
            return root_folder_id

        # Use the record's create_date (or today as fallback).
        from datetime import date as _date
        record_date = None
        if hasattr(record, 'create_date') and record.create_date:
            record_date = record.create_date
        if record_date is None:
            import datetime
            record_date = datetime.datetime.now()

        current_parent_id = root_folder_id

        # ── Year folder ────────────────────────────────────────────────────────
        if self.create_year_folder:
            year_name = str(record_date.year)   # e.g. "2026"
            year_id = self._ensure_onedrive_subfolder(access_token, current_parent_id, year_name)
            if not year_id:
                _logger.error(
                    "[OneDrive Rule '%s'] Could not create year folder '%s'.",
                    self.name, year_name,
                )
                return None
            current_parent_id = year_id
            _logger.debug(
                "[OneDrive Rule '%s'] Using year folder '%s' (id=%s).",
                self.name, year_name, year_id,
            )

        # ── Month folder ───────────────────────────────────────────────────────
        if self.create_month_folder:
            # Format: "May"  (full month name only)
            import calendar
            month_name = calendar.month_name[record_date.month]
            month_id = self._ensure_onedrive_subfolder(access_token, current_parent_id, month_name)
            if not month_id:
                _logger.error(
                    "[OneDrive Rule '%s'] Could not create month folder '%s'.",
                    self.name, month_name,
                )
                return None
            current_parent_id = month_id
            _logger.debug(
                "[OneDrive Rule '%s'] Using month folder '%s' (id=%s).",
                self.name, month_name, month_id,
            )

        return current_parent_id

    def _get_subfolder_name(self, record):
        """
        Evaluate the subfolder_pattern against the given record using safe
        str.format_map() substitution, then sanitise invalid OneDrive chars.
        """
        try:
            # Safely extract ONLY the variables requested in the pattern
            # e.g., "{name}-{id}" -> ["name", "id"]
            requested_fields = [
                fname for _, fname, _, _ in string.Formatter().parse(self.subfolder_pattern)
                if fname
            ]
            
            record_data = {}
            for field_name in requested_fields:
                if not hasattr(record, field_name):
                    record_data[field_name] = ""
                    continue
                    
                val = record[field_name]
                if isinstance(val, (str, int, float, bool)) or val is False:
                    record_data[field_name] = val if val is not False else ""
                elif hasattr(val, "display_name") and len(val) == 1:
                    record_data[field_name] = val.display_name or ""
                elif hasattr(val, "name") and len(val) == 1:
                    record_data[field_name] = val.name or ""
                else:
                    record_data[field_name] = str(val) if val else ""

            subfolder_name = self.subfolder_pattern.format_map(record_data)

        except (KeyError, AttributeError, ValueError) as exc:
            _logger.warning(
                "[OneDrive Rule '%s'] Subfolder pattern error: %s – falling back to id.",
                self.name, exc,
            )
            subfolder_name = f"Record-{record.id}"

        # Sanitise: remove characters disallowed by OneDrive / Windows FS
        for ch in INVALID_CHARS:
            subfolder_name = subfolder_name.replace(ch, "-")

        return subfolder_name.strip()[:128] or f"Record-{record.id}"

    def _ensure_onedrive_subfolder(self, access_token, parent_folder_id, subfolder_name):
        """
        Return the OneDrive ID of *subfolder_name* under *parent_folder_id*,
        creating the folder if it does not already exist.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        children_url = f"{GRAPH_DRIVE_URL}/items/{parent_folder_id}/children"

        # ── Step 1: look for an existing folder with this name ─────────────
        url = children_url
        try:
            while url:
                resp = requests.get(url, headers=headers, timeout=30)
                if resp.status_code != 200:
                    return None
                data = resp.json()
                for child in data.get("value", []):
                    if (
                            child.get("folder") is not None
                            and child.get("name", "").lower() == subfolder_name.lower()
                    ):
                        return child["id"]
                url = data.get("@odata.nextLink")
        except requests.exceptions.RequestException as exc:
            _logger.warning("[OneDrive Rule '%s'] Could not list children of '%s': %s",
                            self.name, parent_folder_id, exc)
            return None

        # ── Step 2: create the folder ───────────────────────────────────────
        payload = {
            "name": subfolder_name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "rename",
        }
        try:
            resp = requests.post(children_url, json=payload, headers=headers, timeout=30)
            if resp.status_code in (200, 201):
                folder_id = resp.json()["id"]
                _logger.info(
                    "[OneDrive Rule '%s'] Created subfolder '%s' (id=%s).",
                    self.name, subfolder_name, folder_id,
                )
                return folder_id
            else:
                _logger.error(
                    "[OneDrive Rule '%s'] Failed to create subfolder '%s': HTTP %s – %s",
                    self.name, subfolder_name, resp.status_code, resp.text,
                )
        except requests.exceptions.RequestException as exc:
            _logger.error(
                "[OneDrive Rule '%s'] Network error creating subfolder '%s': %s",
                self.name, subfolder_name, exc,
            )
        return None

    def _upload_file_to_onedrive(self, access_token, parent_folder_id, filename, datas_b64):
        """
        Upload a file to *parent_folder_id* in OneDrive.
        Uses simple PUT for files ≤ 4 MB, chunked upload-session for larger files.

        :param datas_b64: base64-encoded file content (str / bytes)
        :returns:         OneDrive item ID on success, or None.
        """
        file_bytes = base64.b64decode(datas_b64)
        file_size  = len(file_bytes)

        # Sanitise filename
        safe_name = filename
        for ch in INVALID_CHARS:
            safe_name = safe_name.replace(ch, "-")

        headers = {"Authorization": f"Bearer {access_token}"}

        if file_size <= LARGE_FILE_THRESHOLD:
            return self._simple_upload(headers, parent_folder_id, safe_name, file_bytes)
        else:
            _logger.info(
                "[OneDrive Rule '%s'] '%s' is %.1f MB – using chunked upload session.",
                self.name, safe_name, file_size / (1024 * 1024),
            )
            return self._chunked_upload(headers, parent_folder_id, safe_name, file_bytes)

    def _simple_upload(self, auth_headers, parent_folder_id, filename, file_bytes):
        """PUT a file (≤ 4 MB) directly to OneDrive."""
        url = f"{GRAPH_DRIVE_URL}/items/{parent_folder_id}:/{filename}:/content?@microsoft.graph.conflictBehavior=rename"
        try:
            resp = requests.put(url, headers=auth_headers, data=file_bytes, timeout=60)
            if resp.status_code in (200, 201):
                item_id = resp.json().get("id")
                _logger.info(
                    "[OneDrive Rule '%s'] Uploaded '%s' (%.1f KB).",
                    self.name, filename, len(file_bytes) / 1024,
                )
                return item_id
            else:
                _logger.error(
                    "[OneDrive Rule '%s'] Upload failed for '%s': HTTP %s – %s",
                    self.name, filename, resp.status_code, resp.text,
                )
        except requests.exceptions.RequestException as exc:
            _logger.error(
                "[OneDrive Rule '%s'] Network error uploading '%s': %s",
                self.name, filename, exc,
            )
        return None

    def _chunked_upload(self, auth_headers, parent_folder_id, filename, file_bytes):
        """Upload a large file (> 4 MB) using a Microsoft Graph upload session."""
        session_url = f"{GRAPH_DRIVE_URL}/items/{parent_folder_id}:/{filename}:/createUploadSession"
        session_headers = {**auth_headers, "Content-Type": "application/json"}
        session_payload = {
            "item": {
                "@microsoft.graph.conflictBehavior": "rename",
                "name": filename,
            }
        }

        # ── Create session ─────────────────────────────────────────────────
        try:
            resp = requests.post(
                session_url, json=session_payload, headers=session_headers, timeout=30
            )
            if resp.status_code != 200:
                _logger.error(
                    "[OneDrive Rule '%s'] Could not create upload session for '%s': %s",
                    self.name, filename, resp.text,
                )
                return None
            upload_url = resp.json().get("uploadUrl")
            if not upload_url:
                _logger.error(
                    "[OneDrive Rule '%s'] No uploadUrl returned for '%s'.", self.name, filename
                )
                return None
        except requests.exceptions.RequestException as exc:
            _logger.error(
                "[OneDrive Rule '%s'] Network error creating session for '%s': %s",
                self.name, filename, exc,
            )
            return None

        # ── Send chunks ────────────────────────────────────────────────────
        total_size = len(file_bytes)
        offset = 0
        while offset < total_size:
            chunk = file_bytes[offset: offset + CHUNK_SIZE]
            end   = offset + len(chunk) - 1
            chunk_headers = {
                "Content-Range": f"bytes {offset}-{end}/{total_size}",
                "Content-Length": str(len(chunk)),
            }
            try:
                chunk_resp = requests.put(
                    upload_url, headers=chunk_headers, data=chunk, timeout=120
                )
                status = chunk_resp.status_code
                if status in (200, 201):
                    # Final chunk received — server returns the item
                    return chunk_resp.json().get("id")
                elif status == 202:
                    # More chunks expected
                    offset += len(chunk)
                else:
                    _logger.error(
                        "[OneDrive Rule '%s'] Chunk upload failed at offset %d for '%s': %s",
                        self.name, offset, filename, chunk_resp.text,
                    )
                    return None
            except requests.exceptions.RequestException as exc:
                _logger.error(
                    "[OneDrive Rule '%s'] Network error in chunked upload of '%s': %s",
                    self.name, filename, exc,
                )
                return None
        return None

    def _ensure_document_record(self, config, attachment, onedrive_item_id, subfolder_id, subfolder_name):
        """
        Create a documents.document record for the uploaded file if one does
        not already exist with the same onedrive_id.
        Also ensures the subfolder is represented as a folder document.
        """
        Document = self.env["documents.document"]

        # Skip if the document already exists
        if Document.search_count([("onedrive_id", "=", onedrive_item_id)]):
            return

        existing_doc = Document.sudo().with_context(active_test=False).search(
            [("attachment_id", "=", attachment.id)], limit=1
        )
        if existing_doc:
            existing_doc.with_context(no_onedrive_sync=True).write({
                "onedrive_id": onedrive_item_id,
                "onedrive_parent_id": subfolder_id,
                "onedrive_config_id": config.id,
            })
            return
        # Find the Odoo folder that corresponds to the parent OneDrive folder
        odoo_parent = Document.search(
            [
                ("onedrive_id", "=", self.onedrive_folder_id),
                ("onedrive_config_id", "=", config.id),
            ],
            limit=1,
        )

        # Ensure a subfolder document exists in Odoo
        odoo_subfolder = Document.search(
            [
                ("onedrive_id", "=", subfolder_id),
                ("onedrive_config_id", "=", config.id),
            ],
            limit=1,
        )
        if not odoo_subfolder:
            odoo_subfolder = Document.create({
                "name":             subfolder_name,
                "type":             "folder",
                "folder_id":        odoo_parent.id if odoo_parent else False,
                "onedrive_id":      subfolder_id,
                "onedrive_parent_id": self.onedrive_folder_id,
                "onedrive_config_id": config.id,
            })

        # Create the file document
        Document.create({
            "name":             attachment.name,
            "type":             "binary",
            "attachment_id":    attachment.id,
            "folder_id":        odoo_subfolder.id if odoo_subfolder else False,
            "onedrive_id":      onedrive_item_id,
            "onedrive_parent_id": subfolder_id,
            "onedrive_config_id": config.id,
            "res_model":        attachment.res_model,
            "res_id":           attachment.res_id,
        })

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers: Notification
    # ──────────────────────────────────────────────────────────────────────────

    def _display_notification(self, message, title="Notification", msg_type="info", sticky=False):
        """Return a client-action notification dict."""
        return {
            "type": "ir.actions.client",
            "tag":  "display_notification",
            "params": {
                "title":   title,
                "message": message,
                "type":    msg_type,
                "sticky":  sticky,
            },
        }
