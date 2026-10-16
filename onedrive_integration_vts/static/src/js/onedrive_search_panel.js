/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";
import { DocumentsSearchModel } from "@documents/views/search/documents_search_model";
import { DocumentsSearchPanel } from "@documents/views/search/documents_search_panel";

patch(DocumentsSearchModel.prototype, {
    /**
     * @override
     */
    _ensureCategoryValue(category, valueIds) {
        // Add ONEDRIVE to the list of virtual IDs that should not be JSON.parsed
        const storageItem = browser.localStorage.getItem("searchpanel_documents_document");
        if (storageItem === "ONEDRIVE") {
            category.activeValueId = "ONEDRIVE";
            // Check if ONEDRIVE is a valid reachable value
            // Note: valueIds might not contain ONEDRIVE if it's a virtual root added by search_panel_select_range
            return; 
        }
        return super._ensureCategoryValue(...arguments);
    },

    /**
     * @override
     */
    _getCategoryDomain() {
        const userFolderCategory = this.categories.find(
            (cat) => cat.fieldName === "user_folder_id"
        );
        if (userFolderCategory && userFolderCategory.activeValueId === "ONEDRIVE") {
            return [["user_folder_id", "=", "ONEDRIVE"]];
        }
        return super._getCategoryDomain(...arguments);
    },
});

patch(DocumentsSearchPanel, {
    rootIcons: {
        ...DocumentsSearchPanel.rootIcons,
        ONEDRIVE: "fa-cloud",
    },
});
