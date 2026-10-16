from odoo import models, fields, api, _
from odoo.exceptions import UserError , ValidationError
from odoo.fields import Domain
import requests
import base64
import logging

_logger = logging.getLogger(__name__)

# Base URL for Microsoft Graph Delta API
GRAPH_DELTA_URL = "https://graph.microsoft.com/v1.0/me/drive/root/delta"


class DocumentsDocument(models.Model):
    _inherit = "documents.document"

    onedrive_id = fields.Char(index=True)
    onedrive_parent_id = fields.Char(index=True)
    onedrive_config_id = fields.Many2one("onedrive.configuration", string="OneDrive Configuration", index=True)
    is_deleted = fields.Boolean(default=False)

    @api.model
    def _get_or_create_odoo_root_folder(self, config):

        folder_name = (config.root_folder_name or "").strip()
        if not folder_name:
            return False

        if config.onedrive_root_folder_id and config.onedrive_root_folder_id.active:
            return config.onedrive_root_folder_id

        existing = self.search([
            ("name", "=", folder_name),
            ("type", "=", "folder"),
            ("onedrive_config_id", "=", config.id),
            ("onedrive_id", "=", False),
            ("folder_id", "=", False),
        ], limit=1)

        if existing:
            config.onedrive_root_folder_id = existing
            return existing

        root_folder = self.with_context(skip_onedrive_export=True).create({
            "name": folder_name,
            "type": "folder",
            "folder_id": False,
            "owner_id": False,
            "onedrive_config_id": config.id,
        })
        config.onedrive_root_folder_id = root_folder
        return root_folder

    @api.constrains("name", "folder_id", "type")
    def _check_duplicate_folder_name(self):

        for record in self:

            if record.type != "folder":
                continue

            domain = [
                ("id", "!=", record.id),
                ("type", "=", "folder"),
                ("folder_id", "=", record.folder_id.id),
                ("name", "=ilike", record.name.strip()),
            ]

            duplicate = self.search(domain, limit=1)

            if duplicate:
                raise ValidationError(
                    _("A folder with the same name already exists in this parent folder.")
                )

    # ──────────────────────────────────────────────────────────────────────────
    # DELTA SYNC  (new — called by webhook controller)
    # ──────────────────────────────────────────────────────────────────────────
    @api.model
    def _sync_delta_changes(self, config):
        """
        Fetch ONLY changed files from OneDrive using the Delta API.

        The Delta API is smart — it returns only items that changed since the
        last time we called it. We track where we left off using a 'delta_link'
        stored in the onedrive.subscription record.

        Flow:
          1. If we have a saved delta_link → use it (incremental, fast)
          2. If no delta_link yet → call /delta from scratch (full first run)
          3. Process each changed item (create or update in Odoo)
          4. Save the new delta_link for the next call
        """
        # ── Fix: Always refresh token in background jobs before calling Graph API ──
        config.refresh_onedrive_access_token()

        access_token = config.ms_access_token
        if access_token and access_token.startswith("Bearer "):
            access_token = access_token[len("Bearer "):]

        if not access_token:
            _logger.warning("[OneDrive Delta] No access token for config '%s'. Skipping.", config.name)
            return

        headers = {"Authorization": f"Bearer {access_token}"}
        subscription = config.subscription_ids[:1]

        # Use saved delta_link if available, otherwise start fresh
        url = subscription.delta_link if (subscription and subscription.delta_link) else GRAPH_DELTA_URL

        _logger.info("[OneDrive Delta] Starting delta sync for config '%s'.", config.name)

        changed_count = 0
        next_delta_link = None

        while url:
            try:
                response = requests.get(url, headers=headers, timeout=30)

                if response.status_code == 410:
                    # 410 Gone means our delta_link is too old — reset and start fresh
                    _logger.warning("[OneDrive Delta] Delta link expired. Restarting full delta sync.")
                    if subscription:
                        subscription.delta_link = False
                    url = GRAPH_DELTA_URL
                    continue

                if response.status_code != 200:
                    _logger.error("[OneDrive Delta] API error: %s", response.text)
                    break

                data = response.json()
                items = data.get("value", [])
                changed_count += len(items)

                # Process each changed item (reuses existing logic)
                for item in items:
                    self._process_delta_item(item, config.id, headers)

                # If there are more pages of changes, follow @odata.nextLink
                url = data.get("@odata.nextLink")

                # When @odata.deltaLink appears, we've reached the end — save it
                if "@odata.deltaLink" in data:
                    next_delta_link = data["@odata.deltaLink"]

            except requests.exceptions.RequestException as e:
                _logger.error("[OneDrive Delta] Network error: %s", e)
                break

        # Save the new delta_link for next time
        if next_delta_link and subscription:
            subscription.write({
                "delta_link": next_delta_link,
                "last_sync": fields.Datetime.now(),
            })

        _logger.info("[OneDrive Delta] Sync done. %d item(s) processed for config '%s'.", changed_count, config.name)

    def _process_delta_item(self, item, config_id, headers):
        """
        Process a single changed item returned by the Delta API.
        Creates or updates the corresponding Odoo document.

        This is intentionally simple and reuses the same create/update
        pattern as the existing _import_from_url method.
        """
        onedrive_id = item.get("id")
        onedrive_parent_id = item.get("parentReference", {}).get("id")
        if "root" in item:
            _logger.info("[OneDrive Delta] Skipping root drive item '%s'", item.get("name"))
            return

        # Check if the item was deleted in OneDrive
        if item.get("deleted"):
            existing = self.with_context(active_test=False).search([("onedrive_id", "=", onedrive_id)], limit=1)
            if existing:
                doc_name = existing.name
                doc_config_id = existing.onedrive_config_id.id if existing.onedrive_config_id else False
                try:
                    super(DocumentsDocument, existing).action_archive()
                    existing.write({'is_deleted': True})
                    _logger.info("[OneDrive Delta] Deleted document '%s' from Odoo.", doc_name)
                    self.env["onedrive.sync.history"].create_log(
                        operation="webhook",
                        status="success",
                        message=f"Delta sync: deleted '{doc_name}' from Odoo (removed in OneDrive).",
                        config_id=config_id,
                        file_name=doc_name,
                        onedrive_item_id=onedrive_id,
                    )
                except Exception as e:
                    _logger.info(
                        "[OneDrive Delta] Skipped deleting document '%s' because it was already deleted or locked by Odoo UI: %s",
                        doc_name, e,
                    )
                    self.env["onedrive.sync.history"].create_log(
                        operation="webhook",
                        status="skipped",
                        message=f"Delta sync: could not delete '{doc_name}' from Odoo – already gone or locked: {e}",
                        config_id=config_id,
                        file_name=doc_name,
                        onedrive_item_id=onedrive_id,
                    )
            return

        # Find the parent Odoo folder (if any)
        odoo_parent_folder = False
        if onedrive_parent_id:
            odoo_parent_folder = self.with_context(active_test=False).search([("onedrive_id", "=", onedrive_parent_id)], limit=1)
            if odoo_parent_folder and not odoo_parent_folder.onedrive_parent_id:
                odoo_parent_folder = False
        if not odoo_parent_folder:
            config_obj = self.env["onedrive.configuration"].browse(config_id)
            odoo_parent_folder = self._get_or_create_odoo_root_folder(config_obj)


        # ── Handle FOLDER ─────────────────────────────────────────────────────
        if item.get("folder"):
            existing = self.with_context(active_test=False).search([("onedrive_id", "=", onedrive_id)], limit=1)
            if existing:
                if not existing.active:
                    super(DocumentsDocument, existing).action_unarchive()
                    existing.write({'is_deleted': False})
                # Update name/parent if changed
                vals = {}
                if existing.name != item["name"]:
                    vals["name"] = item["name"]
                if odoo_parent_folder and existing.folder_id.id != odoo_parent_folder.id:
                    vals["folder_id"] = odoo_parent_folder.id
                if vals:
                    existing.with_context(skip_onedrive_export=True).write(vals)
                    self.env["onedrive.sync.history"].create_log(
                        operation="webhook",
                        status="success",
                        message=f"Delta sync: updated folder '{item['name']}' in Odoo.",
                        config_id=config_id,
                        file_name=item["name"],
                        onedrive_item_id=onedrive_id,
                    )
            else:
                self.with_context(skip_onedrive_export=True).create({
                    "name": item["name"],
                    "type": "folder",
                    "folder_id": odoo_parent_folder.id if odoo_parent_folder else False,
                    "onedrive_id": onedrive_id,
                    "owner_id": False,
                    "onedrive_parent_id": onedrive_parent_id,
                    "onedrive_config_id": config_id,
                })
                self.env["onedrive.sync.history"].create_log(
                    operation="webhook",
                    status="success",
                    message=f"Delta sync: Imported folder '{item['name']}' in Odoo.",
                    config_id=config_id,
                    file_name=item["name"],
                    onedrive_item_id=onedrive_id,
                )

        # ── Handle FILE ───────────────────────────────────────────────────────
        elif item.get("file"):
            file_size = item.get("size", 0)
            max_file_size = int(
                self.env["ir.config_parameter"].sudo().get_param(
                    "document.max_fileupload_size",
                    67000000
                )
            )

            if file_size > max_file_size:
                self.env["onedrive.sync.history"].create_log(
                    operation="webhook",
                    status="skipped",
                    message=(
                        f"Delta sync: file '{item['name']}' skipped because "
                        f"its size ({round(file_size/1000000, 2)} MB) exceeds "
                        f"the allowed limit ({max_file_size/1000000} MB)."
                    ),
                    config_id=config_id,
                    file_name=item["name"],
                    onedrive_item_id=onedrive_id,
                )
                return

            download_url = item.get("@microsoft.graph.downloadUrl")
            content_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{onedrive_id}/content"
            existing = self.with_context(active_test=False).search([("onedrive_id", "=", onedrive_id)], limit=1)

            if existing:
                if not existing.active:
                    super(DocumentsDocument, existing).action_unarchive()
                    existing.write({'is_deleted': False})
                vals = {}
                if existing.name != item["name"]:
                    vals["name"] = item["name"]
                if odoo_parent_folder and existing.folder_id.id != odoo_parent_folder.id:
                    vals["folder_id"] = odoo_parent_folder.id
                if vals:
                    existing.with_context(skip_onedrive_export=True).write(vals)

                # Re-download file content (Microsoft /delta may omit downloadUrl)
                try:
                    if download_url:
                        file_res = requests.get(download_url, timeout=60)
                    else:
                        file_res = requests.get(content_url, headers=headers, timeout=60)

                    if file_res.status_code == 200:
                        existing.with_context(skip_onedrive_export=True).write({"datas": base64.b64encode(file_res.content).decode()})
                        self.env["onedrive.sync.history"].create_log(
                            operation="webhook",
                            status="success",
                            message=f"Delta sync: updated file '{item['name']}' in Odoo.",
                            config_id=config_id,
                            file_name=item["name"],
                            onedrive_item_id=onedrive_id,
                        )
                except requests.exceptions.RequestException as e:
                    _logger.warning("[OneDrive Delta] Could not download file '%s': %s", item["name"], e)
                    self.env["onedrive.sync.history"].create_log(
                        operation="webhook",
                        status="failed",
                        message=f"Delta sync: failed to re-download '{item['name']}': {e}",
                        config_id=config_id,
                        file_name=item["name"],
                        onedrive_item_id=onedrive_id,
                    )
            else:
                # We want to create the file in Odoo whether we have content right now or not
                file_content = b""
                try:
                    if download_url:
                        file_res = requests.get(download_url, timeout=60)
                    else:
                        file_res = requests.get(content_url, headers=headers, timeout=60)
                    
                    if file_res.status_code == 200:
                        file_content = file_res.content
                except requests.exceptions.RequestException as e:
                    _logger.warning("[OneDrive Delta] Could not download new file '%s': %s", item["name"], e)
                    self.env["onedrive.sync.history"].create_log(
                        operation="webhook",
                        status="failed",
                        message=f"Delta sync: failed to download new file content '{item['name']}': {e}",
                        config_id=config_id,
                        file_name=item["name"],
                        onedrive_item_id=onedrive_id,
                    )

                # Always create the file record in Odoo so it's visible, even if empty temporarily
                new_doc = self.with_context(skip_onedrive_export=True).create({
                    "name": item["name"],
                    "type": "binary",
                    "datas": base64.b64encode(file_content).decode("utf-8") if file_content else False,
                    "folder_id": odoo_parent_folder.id if odoo_parent_folder else False,
                    "owner_id": False,
                    "onedrive_id": onedrive_id,
                    "onedrive_parent_id": onedrive_parent_id,
                    "onedrive_config_id": config_id,
                })
                
                if file_content:
                    self.env["onedrive.sync.history"].create_log(
                        operation="webhook",
                        status="success",
                        message=f"Delta sync: imported new file '{item['name']}' from OneDrive into Odoo.",
                        config_id=config_id,
                        file_name=item["name"],
                        onedrive_item_id=onedrive_id,
                    )

    # ──────────────────────────────────────────────────────────────────────────
    # EXISTING METHODS (unchanged)
    # ──────────────────────────────────────────────────────────────────────────

    @api.model
    def import_onedrive(self, config, recursive=False):
        """
        Main entry point for importing files from OneDrive.
        Directly imports items into the top level of the OneDrive sidebar category.
        """
        if not config.ms_access_token:
            raise UserError("OneDrive access token not found.")

        headers = {"Authorization": f"Bearer {config.ms_access_token}"}
        # Start importing from the root of the user's OneDrive
        root_url = "https://graph.microsoft.com/v1.0/me/drive/root/children"

        stats = {'folders_created': 0, 'folders_updated': 0, 'files_created': 0, 'files_updated': 0}
        # We pass parent_id=False to import items as top-level Odoo documents (but tagged with config_id)
        self._import_from_url(root_url, headers, config_id=config.id, recursive=recursive, stats=stats)

        message = (
            f"Folders: {stats['folders_created']} Created, {stats['folders_updated']} Updated  |  "
            f"Files: {stats['files_created']} Created, {stats['files_updated']} Updated/Skipped"
        )

        # Log the import summary to sync history
        self.env["onedrive.sync.history"].create_log(
            operation="download",
            status="success",
            message=f"Manual import completed. {message}",
            config_id=config.id,
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "OneDrive Import Successful",
                "message": message,
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            }
        }

    def _import_from_url(self, url, headers, config_id, recursive, stats=None):
        """
        Recursive helper to import items from OneDrive Graph API.
        :param url: The API URL to fetch children from.
        :param parent_id: The Odoo document ID of the parent folder (False for top-level).
        :param config_id: The ID of the OneDrive configuration record.
        """
        if stats is None:
            stats = {'folders_created': 0, 'folders_updated': 0, 'files_created': 0, 'files_updated': 0}

        try:
            while url:
                response = requests.get(url, headers=headers, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    items = data.get("value", [])

                    for item in items:
                        onedrive_id = item.get("id")
                        onedrive_parent_id = item.get("parentReference", {}).get("id")

                        odoo_parent_folder = False
                        if onedrive_parent_id:
                            odoo_parent_folder = self.search([("onedrive_id", "=", onedrive_parent_id)],limit=1)

                        if not odoo_parent_folder:
                            config_obj = self.env["onedrive.configuration"].browse(config_id)
                            odoo_parent_folder = self._get_or_create_odoo_root_folder(config_obj)

                        if item.get("folder"):
                            # Handle folder creation or update
                            existing = self.search([("onedrive_id", "=", onedrive_id)], limit=1)

                            if existing:
                                stats['folders_updated'] += 1
                                # Update parenting if necessary
                                if odoo_parent_folder and existing.folder_id.id != odoo_parent_folder.id:
                                    existing.folder_id = odoo_parent_folder.id
                                if existing.name != item["name"]:
                                    existing.write({
                                        "name": item["name"],
                                    })
                                self.env["onedrive.sync.history"].create_log(
                                    operation="download",
                                    status="success",
                                    message=f"Folder '{item['name']}' updated from OneDrive.",
                                    config_id=config_id,
                                    file_name=item["name"],
                                    onedrive_item_id=onedrive_id,
                                )
                            else:
                                self.create({
                                    "name": item["name"],
                                    "type": "folder",
                                    "folder_id": odoo_parent_folder.id if odoo_parent_folder else False,
                                    "owner_id": False,
                                    "onedrive_id": onedrive_id,
                                    "onedrive_parent_id": onedrive_parent_id,
                                    "onedrive_config_id": config_id,
                                })
                                stats['folders_created'] += 1
                                self.env["onedrive.sync.history"].create_log(
                                    operation="download",
                                    status="success",
                                    message=f"Folder '{item['name']}' imported from OneDrive.",
                                    config_id=config_id,
                                    file_name=item["name"],
                                    onedrive_item_id=onedrive_id,
                                )


                            if recursive:
                                child_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{onedrive_id}/children"
                                self._import_from_url(child_url, headers,config_id, recursive=recursive,stats=stats)

                        elif item.get("file"):
                            file_size = item.get("size",0)
                            max_file_size = int(
                                self.env["ir.config_parameter"].sudo().get_param(
                                    "document.max_fileupload_size",
                                    67000000
                                )
                            )
                            if file_size > 	max_file_size:
                                self.env["onedrive.sync.history"].create_log(
                                    operation="download",
                                    status="skipped",
                                    message=(
                                        f"File '{item['name']}' skipped because "
                                        f"its size ({round(file_size/1000000,2)} MB) exceeds "
                                        f"the allowed limit ({max_file_size/1000000} MB )."
                                    ),
                                    config_id=config_id,
                                    file_name=item["name"],
                                    onedrive_item_id=onedrive_id,
                                )
                                continue

                            # Handle file creation
                            existing = self.search([("onedrive_id", "=", onedrive_id)], limit=1)
                            download_url = item.get("@microsoft.graph.downloadUrl")
                            if existing:
                                if odoo_parent_folder and existing.folder_id.id != odoo_parent_folder.id:
                                    existing.folder_id = odoo_parent_folder.id
                                if existing.name != item["name"]:
                                    existing.write({
                                        "name": item["name"],
                                    })
                                if download_url:
                                    file_res = requests.get(download_url, timeout=60)

                                    if file_res.status_code == 200:
                                        existing.write({
                                            "datas": base64.b64encode(file_res.content).decode(),
                                        })
                                        stats['files_updated'] += 1
                                        self.env["onedrive.sync.history"].create_log(
                                            operation="download",
                                            status="success",
                                            message=f"File '{item['name']}' updated from OneDrive.",
                                            config_id=config_id,
                                            file_name=item["name"],
                                            onedrive_item_id=onedrive_id,
                                        )
                                    else:
                                        self.env["onedrive.sync.history"].create_log(
                                            operation="download",
                                            status="failed",
                                            message=(
                                                f"Failed to download file '{item['name']}': {file_res.text}"),
                                            config_id=config_id,
                                            file_name=item["name"],
                                            onedrive_item_id=onedrive_id,
                                        )

                            else:
                                if download_url:
                                    file_res = requests.get(download_url, timeout=60)
                                    if file_res.status_code == 200:
                                        self.create({
                                        "name": item["name"],
                                        "type": "binary",
                                        "datas": base64.b64encode(file_res.content).decode("utf-8"),
                                        "folder_id": odoo_parent_folder.id if odoo_parent_folder else False,
                                        "owner_id": False,
                                        "onedrive_id": onedrive_id,
                                        "onedrive_parent_id": onedrive_parent_id,
                                        "onedrive_config_id": config_id,
                                    })
                                        stats['files_created'] += 1
                                        self.env["onedrive.sync.history"].create_log(
                                            operation="download",
                                            status="success",
                                            message=f"File '{item['name']}' imported from OneDrive.",
                                            config_id=config_id,
                                            file_name=item["name"],
                                            onedrive_item_id=onedrive_id,
                                        )
                                    else:
                                        self.env["onedrive.sync.history"].create_log(
                                            operation="download",
                                            status="failed",
                                            message=(f"Failed to download file '{item['name']}': {file_res.text}"),
                                            config_id=config_id,
                                            file_name=item["name"],
                                            onedrive_item_id=onedrive_id,
                                        )
                    url = data.get("@odata.nextLink")

                else:
                    self.env["onedrive.sync.history"].create_log(
                        operation="download",
                        status="failed",
                        message=(f"Failed to fetch OneDrive items. Response: {response.text}"),
                        config_id=config_id,
                    )
                    break

        except Exception as e:
            self.env["onedrive.sync.history"].create_log(
                operation="download",
                status="failed",
                message=f"OneDrive import failed: {str(e)}",
                config_id=config_id,
            )

        return stats

    @api.depends('onedrive_config_id', 'folder_id', 'owner_id', 'onedrive_id', 'onedrive_parent_id')
    def _compute_user_folder_id(self):
        """
        Compute the virtual parent directory for the Documents search panel.
        Assigns documents tagged with a OneDrive configuration (and no Odoo parent) to the 'OneDrive' sidebar category.
        Also hides legacy OneDrive root folders from the sidebar.
        """
        super()._compute_user_folder_id()
        for record in self:
            # 1. If this document is a top-level OneDrive item, move it to the 'ONEDRIVE' sidebar category.
            if record.onedrive_config_id and not record.folder_id:
                record.user_folder_id = 'ONEDRIVE'
            # 2. Hide legacy OneDrive root folders by ensuring they don't have a user_folder_id.
            elif record.onedrive_id and not record.folder_id and not record.onedrive_parent_id:
                record.user_folder_id = False

    def _search_user_folder_id(self, operator, operand):
        """
        Search implementation for the virtual 'ONEDRIVE' category.
        Ensures clicking 'OneDrive' in the sidebar filters for all documents tagged with a OneDrive configuration.
        """
        if operator in ('in', 'child_of'):
            values = {operand} if isinstance(operand, str) else set(operand)
            if 'ONEDRIVE' in values:
                # Match documents tagged with any OneDrive configuration that have no Odoo parent
                domain = Domain([('onedrive_config_id', '!=', False), ('folder_id', '=', False)])

                if operator == 'child_of':
                    # Include the entire subtree of these top-level items
                    top_level = self.with_context(active_test=False).sudo().search_fetch(domain, ['type'])
                    top_level_folders = top_level.filtered(lambda d: d.type == 'folder')
                    return Domain('id', 'in', top_level.ids) | Domain('folder_id', 'child_of', top_level_folders.ids)
                return domain
        return super()._search_user_folder_id(operator, operand)

    @api.model
    def search_panel_select_range(self, field_name, **kwargs):
        """
        Inject the 'OneDrive' root category into the sidebar data fetched by the web client.
        """
        result = super().search_panel_select_range(field_name, **kwargs)
        if field_name == 'user_folder_id' and not self.env.user.share:
            # Define the visual appearance of the OneDrive sidebar item
            onedrive_root = {
                'display_name': _("OneDrive"),
                'id': 'ONEDRIVE',
                'description': _("Documents synced from OneDrive."),
                'bold': True,
                'childrenIds': [],
                'parentId': False,
                'user_permission': 'edit',
            }
            # Append it to the list of sidebar roots (Company, My Drive, etc.)
            if not any(v['id'] == 'ONEDRIVE' for v in result.get('values', [])):
                result['values'].append(onedrive_root)
            for val in result.get('values', []):
                if (
                        isinstance(val.get('id'), int)
                        and val.get('parentId') is False
                        and val.get('id') in self.env['onedrive.configuration'].search([]).mapped(
                    'onedrive_root_folder_id.id')
                ):
                    val['parentId'] = 'ONEDRIVE'
        return result

    def action_archive(self):
        for doc in self:
            if  doc.onedrive_config_id and doc.onedrive_config_id.state == "connected" and doc.onedrive_config_id.auto_delete:
                if doc.onedrive_id:
                    doc.delete_from_onedrive()
                elif doc == doc.onedrive_config_id.onedrive_root_folder_id:
                    for child in self.search([("folder_id", "=", doc.id), ("onedrive_id", "!=", False)]):
                        child.delete_from_onedrive()

        return super().action_archive()

    def delete_from_onedrive(self):
        if not self.onedrive_id or not self.onedrive_config_id:
            return
        config_id = self.onedrive_config_id
        try:
            url = f"https://graph.microsoft.com/v1.0/me/drive/items/{self.onedrive_id}"
            headers = {"Authorization": f"Bearer {config_id.ms_access_token}"}
            response = requests.delete(url, headers=headers, timeout=30)
            if response.status_code == 204:
                self.is_deleted = True
                self.env["onedrive.sync.history"].create_log(
                    operation="delete",
                    status="success",
                    message=f"'{self.name}' successfully deleted from OneDrive.",
                    config_id=config_id.id,
                    file_name=self.name,
                    onedrive_item_id=self.onedrive_id,
                )
            else:
                self.env["onedrive.sync.history"].create_log(
                    operation="delete",
                    status="failed",
                    message=f"OneDrive API returned HTTP {response.status_code} while deleting '{self.name}': {response.text}",
                    config_id=config_id.id,
                    file_name=self.name,
                    onedrive_item_id=self.onedrive_id,
                )
        except Exception as e:
            self.env["onedrive.sync.history"].create_log(
                operation="delete",
                status="failed",
                message=f"Exception while deleting '{self.name}' from OneDrive: {str(e)}",
                config_id=config_id.id,
                file_name=self.name,
                onedrive_item_id=self.onedrive_id,
            )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)

        for record in records:
            if not record.onedrive_config_id and record.folder_id and record.folder_id.onedrive_config_id:
                record.onedrive_config_id = record.folder_id.onedrive_config_id
            record.export_to_onedrive()

        return records

    def export_to_onedrive(self):
        if self.env.context.get("skip_onedrive_export"):
            return
        for record in self:
            config = record.onedrive_config_id
            if not config or not config.ms_access_token or record.onedrive_id:
                continue

            headers = {"Authorization": f"Bearer {config.ms_access_token}"}

            chain = []
            parent = record.folder_id

            while parent:
                chain.append(parent)
                parent = parent.folder_id

            # Create parents from top → bottom
            for folder in reversed(chain):
                if folder.onedrive_id or not folder.folder_id:
                    continue

                parent_onedrive_id = folder.folder_id.onedrive_id if folder.folder_id else None

                if parent_onedrive_id:
                    url = f"https://graph.microsoft.com/v1.0/me/drive/items/{parent_onedrive_id}/children"
                else:
                    url = "https://graph.microsoft.com/v1.0/me/drive/root/children"

                payload = {
                    "name": folder.name,
                    "folder": {},
                    "@microsoft.graph.conflictBehavior": "rename",
                }

                try:
                    res = requests.post(url,json=payload,headers={**headers, "Content-Type": "application/json"},timeout=30)

                    if res.status_code in (200, 201):
                        data = res.json()
                        folder.write({
                            "onedrive_id": data["id"],
                            "onedrive_parent_id": data.get("parentReference", {}).get("id"),
                        })
                        self.env["onedrive.sync.history"].create_log(
                            operation="folder",
                            status="success",
                            message=f"Folder '{folder.name}' created in OneDrive.",
                            config_id=record.onedrive_config_id.id if record.onedrive_config_id else False,
                            file_name=folder.name,
                            onedrive_item_id=data["id"],
                        )
                    else:
                        self.env["onedrive.sync.history"].create_log(
                            operation="folder",
                            status="failed",
                            message=f"Failed to create folder '{folder.name}' in OneDrive: {res.text}",
                            config_id=record.onedrive_config_id.id if record.onedrive_config_id else False,
                            file_name=folder.name,
                        )

                except Exception as e:
                    self.env["onedrive.sync.history"].create_log(
                        operation="folder",
                        status="failed",
                        message=f"Failed to create folder '{folder.name}' in OneDrive: {e}",
                        config_id=record.onedrive_config_id.id if record.onedrive_config_id else False,
                        file_name=folder.name,
                    )

            # -----------------------------
            # STEP 2: UPLOAD CURRENT RECORD
            # -----------------------------
            parent_onedrive_id = record.folder_id.onedrive_id if record.folder_id else None

            # FOLDER
            if record.type == "folder":
                if parent_onedrive_id:
                    url = f"https://graph.microsoft.com/v1.0/me/drive/items/{parent_onedrive_id}/children"
                else:
                    url = "https://graph.microsoft.com/v1.0/me/drive/root/children"

                payload = {
                    "name": record.name,
                    "folder": {},
                    "@microsoft.graph.conflictBehavior": "rename",
                }

                try:
                    res = requests.post(url,json=payload,headers={**headers, "Content-Type": "application/json"},timeout=30)

                    if res.status_code in (200, 201):
                        data = res.json()
                        record.write({
                            "onedrive_id": data["id"],
                            "onedrive_parent_id": data.get("parentReference", {}).get("id"),
                        })
                        self.env["onedrive.sync.history"].create_log(
                            operation="folder",
                            status="success",
                            message=f"Folder '{record.name}' created in OneDrive.",
                            config_id=record.onedrive_config_id.id if record.onedrive_config_id else False,
                            file_name=record.name,
                            onedrive_item_id=data["id"],
                        )
                    else:
                        self.env["onedrive.sync.history"].create_log(
                            operation="folder",
                            status="failed",
                            message=f"Failed to create folder '{record.name}' in OneDrive: {res.text}",
                            config_id=record.onedrive_config_id.id if record.onedrive_config_id else False,
                            file_name=record.name,
                        )

                except Exception as e:
                    self.env["onedrive.sync.history"].create_log(
                        operation="folder",
                        status="failed",
                        message=f"Exception while creating folder '{record.name}' in OneDrive: {str(e)}",
                        config_id=record.onedrive_config_id.id if record.onedrive_config_id else False,
                        file_name=record.name,
                    )

            # FILE
            elif record.type == "binary" and record.datas:
                if parent_onedrive_id:
                    url = (
                        f"https://graph.microsoft.com/v1.0/me/drive/items/{parent_onedrive_id}:/{record.name}:/content?@microsoft.graph.conflictBehavior=rename"
                    )
                else:
                    url = (
                        f"https://graph.microsoft.com/v1.0/me/drive/root:/{record.name}:/content?@microsoft.graph.conflictBehavior=rename"
                    )

                try:
                    file_content = base64.b64decode(record.datas)

                    res = requests.put(url,data=file_content,headers={**headers, "Content-Type": "application/octet-stream"},timeout=60)

                    if res.status_code in (200, 201):
                        data = res.json()
                        record.write({
                            "name": data["name"],
                            "onedrive_id": data["id"],
                            "onedrive_parent_id": data.get("parentReference", {}).get("id"),
                        })
                        self.env["onedrive.sync.history"].create_log(
                            operation="upload",
                            status="success",
                            message=f"File '{record.name}' uploaded to OneDrive",
                            config_id=record.onedrive_config_id.id if record.onedrive_config_id else False,
                            file_name=record.name,
                            onedrive_item_id=data["id"],
                        )
                    else:
                        self.env["onedrive.sync.history"].create_log(
                            operation="upload",
                            status="failed",
                            message=f"Failed to upload file '{record.name}' to OneDrive: {res.text}",
                            config_id=record.onedrive_config_id.id if record.onedrive_config_id else False,
                            file_name=record.name,
                        )

                except Exception as e:
                    self.env["onedrive.sync.history"].create_log(
                        operation="upload",
                        status="failed",
                        message=f"Exception while uploading file '{record.name}' to OneDrive: {str(e)}",
                        config_id=record.onedrive_config_id.id if record.onedrive_config_id else False,
                        file_name=record.name,
                    )

    def write(self, vals):
        if vals.get("user_folder_id") == "ONEDRIVE":
            # Block moving anything to the same level as the Odoo root folder
            for record in self:
                config = record.onedrive_config_id
                if config and config.onedrive_root_folder_id:
                    raise ValidationError(
                        _("You cannot move files or folders to this level. Please place them inside '%s'.")
                        % config.onedrive_root_folder_id.name
                    )
            vals.pop("user_folder_id", None)
            vals["folder_id"] = False

        self.update_to_onedrive(vals)
        res = super().write(vals)
        return res

    def update_to_onedrive(self, vals):
        if self.env.context.get("skip_onedrive_export"):
            return

        for record in self:

            if not record.onedrive_id or not record.onedrive_config_id:
                continue
            config = record.onedrive_config_id
            if not config.ms_access_token:
                continue

            update_payload = {}

            if "name" in vals:
                update_payload["name"] = vals["name"]

            if "user_folder_id" in vals and vals.get("user_folder_id"):

                parent_folder = self.browse(int(vals["user_folder_id"]))
                if parent_folder.onedrive_id:
                    update_payload["parentReference"] = {
                        "id": parent_folder.onedrive_id
                    }
                else:
                    update_payload["parentReference"] = {
                        "path": "/drive/root:"
                    }

            if not update_payload:
                continue

            try:
                url = f"https://graph.microsoft.com/v1.0/me/drive/items/{record.onedrive_id}"

                headers = {
                    "Authorization": f"Bearer {config.ms_access_token}",
                    "Content-Type": "application/json",
                }

                response = requests.patch(url,json=update_payload,headers=headers,timeout=30,)

                if response.status_code in (200, 201):
                    data=response.json()
                    old_name = record.name
                    new_name = data.get("name")
                    parent_ref = data.get("parentReference", {})

                    parent_name = parent_ref.get("name", "Unknown Folder")

                    if parent_name == "Documents" and parent_ref.get("path") == "/drive/root:":
                        parent_name = "Root"

                    if "name" in vals:
                        message = f"'{old_name}' renamed to '{new_name}' in OneDrive."
                    else:
                        message = (
                            f"'{new_name}' moved to folder '{parent_name}' in OneDrive."
                        )

                    self.env["onedrive.sync.history"].create_log(
                        operation="update",
                        status="success",
                        message=message,
                        config_id=config.id,
                        file_name=record.name,
                        onedrive_item_id=record.onedrive_id,
                    )

                else:
                    self.env["onedrive.sync.history"].create_log(
                        operation="update",
                        status="failed",
                        message=(f"Failed to update '{record.name}' in OneDrive: {response.text}"),
                        config_id=config.id,
                        file_name=record.name,
                        onedrive_item_id=record.onedrive_id,
                    )

            except Exception as e:
                self.env["onedrive.sync.history"].create_log(
                    operation="update",
                    status="failed",
                    message=(f"Exception while updating '{record.name}' in OneDrive: {str(e)}"),
                    config_id=config.id,
                    file_name=record.name,
                    onedrive_item_id=record.onedrive_id,
                )

    def action_unarchive(self):
        for doc in self:
            if doc.onedrive_config_id and doc.onedrive_config_id.state == "connected":
                if doc.onedrive_id and doc.is_deleted:
                    doc.restore_from_onedrive()
                elif doc == doc.onedrive_config_id.onedrive_root_folder_id:
                    for child in self.with_context(active_test=False).search(
                            [("folder_id", "=", doc.id), ("onedrive_id", "!=", False), ("is_deleted", "=", True)]):
                        child.restore_from_onedrive()

        return super().action_unarchive()

    def restore_from_onedrive(self):
        if not self.onedrive_id or not self.onedrive_config_id:
            return

        config_id = self.onedrive_config_id

        try:
            headers = {
                "Authorization": f"Bearer {config_id.ms_access_token}"
            }
            restore_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{self.onedrive_id}/restore"
            restore_response = requests.post(restore_url, headers=headers, timeout=30)
            if restore_response.status_code in [200, 204]:
                self.is_deleted  = False
                self.env["onedrive.sync.history"].create_log(
                    operation="restore",
                    status="success",
                    message=(
                        f"'{self.name}' successfully restored "
                        f"from OneDrive."
                    ),
                    config_id=config_id.id,
                    file_name=self.name,
                    onedrive_item_id=self.onedrive_id,
                )

            else:
                self.env["onedrive.sync.history"].create_log(
                    operation="restore",
                    status="failed",
                    message=(
                        f"OneDrive API returned HTTP "
                        f"{restore_response.status_code} while "
                        f"restoring '{self.name}': "
                        f"{restore_response.text}"
                    ),
                    config_id=config_id.id,
                    file_name=self.name,
                    onedrive_item_id=self.onedrive_id,
                )
        except Exception as e:
            self.env["onedrive.sync.history"].create_log(
                    operation="restore",
                    status="failed",
                    message=(
                        f"Exception while restoring "
                        f"'{self.name}' from OneDrive: "
                        f"{str(e)}"
                    ),
                    config_id=config_id.id,
                    file_name=self.name,
                    onedrive_item_id=self.onedrive_id,
                )


