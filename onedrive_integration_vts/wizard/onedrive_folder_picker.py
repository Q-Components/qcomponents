# -*- coding: utf-8 -*-
import requests
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

GRAPH_DRIVE_URL = "https://graph.microsoft.com/v1.0/me/drive"


class OnedriveFolderPicker(models.TransientModel):
    _name = "onedrive.folder.picker"
    _description = "OneDrive Folder Picker Wizard"

    config_id = fields.Many2one("onedrive.configuration", string="OneDrive Config", required=True)
    rule_id = fields.Many2one("onedrive.folder.rule", string="Folder Rule", required=True)

    current_folder_id = fields.Char(string="Current Folder ID", default="root")
    current_folder_name = fields.Char(string="Current Location", default="Root")
    parent_folder_id = fields.Char(string="Parent Folder ID")

    item_ids = fields.One2many("onedrive.folder.picker.item", "picker_id", string="Folders")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "rule_id" in self.env.context:
            rule = self.env["onedrive.folder.rule"].browse(self.env.context.get("rule_id"))
            res["rule_id"] = rule.id
            if rule.onedrive_config_id:
                res["config_id"] = rule.onedrive_config_id.id
        return res

    def _get_token(self):
        self.ensure_one()
        self.config_id.refresh_onedrive_access_token()
        token = self.config_id.ms_access_token or ""
        if token.startswith("Bearer "):
            token = token[len("Bearer "):]
        return token.strip()

    def _fetch_folders(self, folder_id="root"):
        """Fetches folders from the Graph API for the given folder_id."""
        self.ensure_one()
        token = self._get_token()
        if not token:
            raise UserError(_("No valid access token. Please reconnect OneDrive."))

        # 1. Fetch children (folders only)
        # We use $filter=folder ne null to only get folders, not files.
        children_url = f"{GRAPH_DRIVE_URL}/items/{folder_id}/children?$filter=folder ne null&$select=id,name,parentReference,webUrl&$top=100"
        
        try:
            resp = requests.get(children_url, headers={"Authorization": f"Bearer {token}"}, timeout=10)
            if resp.status_code != 200:
                raise UserError(_("Failed to fetch folders from OneDrive: %s") % resp.text)
            data = resp.json()
            items = data.get("value", [])
        except Exception as e:
            raise UserError(_("Error connecting to Microsoft Graph: %s") % e)

        # 2. Fetch the current folder's metadata to get its name and parent
        parent_id = False
        folder_name = "Root"
        if folder_id != "root":
            try:
                meta_url = f"{GRAPH_DRIVE_URL}/items/{folder_id}?$select=id,name,parentReference"
                meta_resp = requests.get(meta_url, headers={"Authorization": f"Bearer {token}"}, timeout=5)
                if meta_resp.status_code == 200:
                    meta_data = meta_resp.json()
                    folder_name = meta_data.get("name", folder_name)
                    parent_ref = meta_data.get("parentReference", {})
                    # If the folder's parent is the root drive, the parentReference.id might be the drive ID.
                    # Usually, if parentReference contains "path", it helps.
                    # We will just use the parent's ID if it exists.
                    parent_id = parent_ref.get("id")
            except Exception:
                pass

        # 3. Update the picker record
        self.write({
            "current_folder_id": folder_id,
            "current_folder_name": folder_name,
            "parent_folder_id": parent_id,
        })

        # 4. Replace item_ids
        self.item_ids.unlink()
        new_items = []
        for item in items:
            new_items.append((0, 0, {
                "name": item.get("name"),
                "onedrive_id": item.get("id"),
            }))
        self.write({"item_ids": new_items})

    def action_go_back(self):
        self.ensure_one()
        if self.parent_folder_id:
            self._fetch_folders(self.parent_folder_id)
        else:
            # Fallback to root
            self._fetch_folders("root")
        return self._reopen_wizard()

    def action_select_current(self):
        """Allows selecting the directory we are currently viewing."""
        self.ensure_one()
        if not self.current_folder_id or self.current_folder_id == "root":
            raise UserError(_("Cannot select the drive root directly. Please select a specific folder."))
            
        self.rule_id.write({
            "onedrive_folder_id": self.current_folder_id,
            "onedrive_folder_name": self.current_folder_name,
        })
        return {"type": "ir.actions.act_window_close"}

    def _reopen_wizard(self):
        """Returns action to keep the wizard open."""
        return {
            "type": "ir.actions.act_window",
            "name": "Browse OneDrive",
            "res_model": "onedrive.folder.picker",
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }


class OnedriveFolderPickerItem(models.TransientModel):
    _name = "onedrive.folder.picker.item"
    _description = "OneDrive Folder Picker Item"

    picker_id = fields.Many2one("onedrive.folder.picker", required=True, ondelete="cascade")
    name = fields.Char(string="Folder Name", required=True)
    onedrive_id = fields.Char(string="Folder ID", required=True)

    def action_open_folder(self):
        self.ensure_one()
        # Spawn a new picker so we don't destroy `self` while Odoo is still processing the click
        new_picker = self.env["onedrive.folder.picker"].create({
            "config_id": self.picker_id.config_id.id,
            "rule_id": self.picker_id.rule_id.id,
        })
        new_picker._fetch_folders(self.onedrive_id)
        return new_picker._reopen_wizard()

    def action_select_folder(self):
        self.ensure_one()
        self.picker_id.rule_id.write({
            "onedrive_folder_id": self.onedrive_id,
            "onedrive_folder_name": self.name,
        })
        return {"type": "ir.actions.act_window_close"}
