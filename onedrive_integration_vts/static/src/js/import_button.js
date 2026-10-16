/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { DocumentsKanbanController } from "@documents/views/kanban/documents_kanban_controller";
import { DocumentsListController } from "@documents/views/list/documents_list_controller";

function openImportWizard() {
    this.env.services.action.doAction(
        "onedrive_integration_vts.action_onedrive_import_wizard"
    );
}

patch(DocumentsKanbanController.prototype, {
    onClickImport: openImportWizard,
});

patch(DocumentsListController.prototype, {
    onClickImport: openImportWizard,
});

