/** @odoo-module **/
import { SearchBar } from "@web/search/search_bar/search_bar";
import { SearchModel } from "@web/search/search_model";
import { SearchBarMenu } from "@web/search/search_bar_menu/search_bar_menu";
import { rpcBus } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { domainFromTree } from "@web/core/tree_editor/domain_from_tree";

patch(SearchModel.prototype, {
    setup(services) {
        super.setup(...arguments);
        this.filter_history = [];
    },
    async load(config) {
        super.load(config);
        await this.load_history_data()
    },
    async _notify() {
        if (this.blockNotification) {
            return;
        }
        await this.load_history_data()
        this._reset();
        await this._reloadSections();
        this.trigger("update");
    },
    async load_history_data() {
        this.filter_history = await this.orm.call("filter.search.history", "get_filter_history", [[],this.resModel])
    },
    get history_data() {
        return this.filter_history || []
    },
    createNewFilters(prefilters) {
        // custom======================
        this.createNewFavoriteHistory(prefilters)
        // ======================
        return super.createNewFilters(prefilters);
    },
    getTooltipString(data) {
        if(data){
            return data.map(item => item.tooltip || item.description).join(', ');
        }else{
            return '';
        }
    },
    // custom method
    async createNewFavoriteHistory(prefilters) { 
        let description = this.getTooltipString(prefilters)
        if(!description){
            return;
        }
        let params = {
            "description": description,
            "isDefault": false,
            "isShared": false,
            "embeddedActionId": false
        }
        let domain = prefilters[0].domain;
        const { preFavorite, irFilter } = this._getIrFilterDescription(params); 
        irFilter.domain = domain;
        await this._createIrFiltersHistory(irFilter);
    },
    // custom method
    async _createIrFiltersHistory(irFilter) {
        if(!irFilter.domain){
            return;
        }
        const serverSideIds = await this.orm.call("filter.search.history", "create_filter", [irFilter]);
        rpcBus.trigger("CLEAR-CACHES", "get_views");
        this._notify();
    },
    async get_str(domain){
        let context;
        const tree = await this.treeProcessor.treeFromDomain(
            this.resModel,
            domain,
            !this.isDebugMode
        );
        const trees =
            !tree.negate &&
            tree.type === "connector" &&
            tree.value === "&" &&
            tree.children.length > 0
                ? tree.children
                : [tree];
        const promises = trees.map(async (tree) => {
            const [description, tooltip] = await Promise.all([
                this.treeProcessor.getDomainTreeDescription(this.resModel, tree),
                this.treeProcessor.getDomainTreeTooltip(this.resModel, tree),
            ]);
            const preFilter = {
                description,
                tooltip,
                domain: domainFromTree(tree),
                invisible: "True",
                type: "filter",
            };
            if (context) {
                preFilter.context = context;
            }
            return preFilter;
        });
        const preFilters = await Promise.all(promises);
        return preFilters
    }
});

patch(SearchBar.prototype, {
    selectItem(item) {
        if (item.isAddCustomFilterButton) {
            return this.env.searchModel.spawnCustomFilterDialog();
        }
        const searchItem = this.getSearchItem(item.searchItemId);
        if (
            (searchItem.fieldType === "selection" && !item.isChild) ||
            (searchItem.type === "field" && searchItem.fieldType === "properties") ||
            (searchItem.type === "field_property" && item.unselectable)
        ) {
            this.toggleItem(item, !item.isExpanded);
            return;
        }

        if (!item.unselectable) {
            const { searchItemId, label, operator, value } = item;
            this.env.searchModel.addAutoCompletionValues(searchItemId, { label, operator, value });
        }
        // custom====================== 
        debugger
        let domain = this.env.searchModel._getDomain({raw: true, withGlobal: false }).toString() || '[]';
        let description = item.searchItemDescription +" : "+item.value;
        let str = this.env.searchModel.get_str(domain)
        let self = this;
        str.then(function(res){ 
            let values = [{
                'description':description,
                'domain':domain
            }];
            self.env.searchModel.createNewFavoriteHistory(values)
            if (item.loadMore) {
                item.loadMore();
            } else {
                self.inputDropdownState.close();
                self.resetState();
            }
        }) 
    },
    get_history_value(filter=[],value=''){
        return [{
            domain :filter.filterDomain?.replace(/\bself\b/g, `'${value}'`),
            description:filter.description +": "+ value       
        }]
    }
});

patch(SearchBarMenu.prototype, {
    onFilterSelected({ itemId, optionId }) {
        if (optionId) {
            this.env.searchModel.toggleDateFilter(itemId, optionId);
        } else {
            this.env.searchModel.toggleSearchItem(itemId);
        }
        let env_filters = this.env.searchModel.getSearchItems((searchItem) =>["filter"].includes(searchItem.type))
        let filter = env_filters.filter(item => item.id == itemId);
        if(filter.length){
            this.env.searchModel.createNewFavoriteHistory(filter)
        }
    },
    get_search_history(){
        return this.env.searchModel.history_data;
    },
    click_filter(filter){  
        this.env.searchModel.splitAndAddDomain(filter.domain, undefined);
    },
    async click_remove_filter(filter){
        let res = await this.env.searchModel.orm.call("filter.search.history", "unlink_filter", [filter]);
        this.env.searchModel._notify();
    }
});