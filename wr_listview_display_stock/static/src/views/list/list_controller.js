/** @odoo-module **/

import { listView } from '@web/views/list/list_view';
import { ListController } from '@web/views/list/list_controller';
import fieldUtils from 'web.field_utils';

export class InheritListController extends ListController {
    getProductQuantity(){
        var total_qty = 0;
        console.log("this >>>>>>>> ", this.model.rootParams);
        this.model.root.selection.map(function(rec){
            total_qty += rec.data.qty_available;
        });
        return fieldUtils.format.float(total_qty, null);
    }
    get isVisibleQuantity(){
        return this.model.rootParams && this.model.rootParams.resModel == 'product.product' && this.model.rootParams.viewMode == 'list';
    }
}

listView.Controller = InheritListController;