/** @odoo-module **/

import { Dialog } from "@web/core/dialog/dialog";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.QuickShopTemplate = publicWidget.Widget.extend({
    selector: ".oe_quick_shop_view",
    template: "QuickShopTemplate",

    init() {
        this.data = [];
        this.term = "";
        this.limit = 20;
        this.offset = 0;
        this.view_type = "grid";

        this.filters = {
            featured: "Featured",
            newest_arrivals: "Newest Arrivals",
            name_a_z: "Name (A-Z)",
            price_low_high: "Price - Low to High",
            price_high_low: "Price - High to Low",
        };

        this.active_filter = "newest_arrivals";

        this._super(...arguments);
    },

    willStart() {
        return this.load_quick_shop_products();
    },

    start() {
        return this._super(...arguments).then(() => {
            $(".website-loader").fadeOut("slow");
            this.el.querySelector('[type="search"]')?.focus();
        });
    },

    events: {
        "click .pagination-prev-btn": "_clickPaginationPrevButton",
        "click .pagination-next-btn": "_clickPaginationNextButton",
        "keyup input[type='search']": "_keyupSearchProduct",
        "click a.js_decrease_qty": "_clickDecreaseQty",
        "click a.js_increase_qty": "_clickIncreaseQty",
        "click a.add_to_cart": "_clickAddToCart",
        "click button.term_search_btn": "_clickTermSearch",
        "click label.o_view_type": "_clickViewType",
        "click a.quick_shop_filter": "_clickQuickShopFilter",
    },

    _clickPaginationPrevButton(ev) {
        ev.preventDefault();

        if (this.data?.current_offset > 1) {
            this.offset = this.data.current_offset - 1 - this.limit;
        }

        this.load_quick_shop_products().then(() => this.renderElement());
    },

    _clickPaginationNextButton(ev) {
        ev.preventDefault();

        if (this.data?.next_offset <= this.data.max_offset) {
            this.offset = this.data.next_offset;
        }

        this.load_quick_shop_products().then(() => this.renderElement());
    },

    _clickDecreaseQty(ev) {
        ev.preventDefault();
        const input = $('input[name="product_qty"]');
        const value = Number(input.val()) || 0;

        if (value > 0) input.val(value - 1);
    },

    _clickIncreaseQty(ev) {
        ev.preventDefault();
        const input = $('input[name="product_qty"]');
        const value = Number(input.val()) || 0;
        input.val(value + 1);
    },

    _keyupSearchProduct(ev) {
        if (ev.keyCode !== 13) return;

        this.term = $(ev.currentTarget).val() || "";
        this.offset = 0;

        this.load_quick_shop_products().then(() => this.renderElement());
    },

    async _clickAddToCart(ev) {
        ev.preventDefault();

        const product_id = Number($(ev.currentTarget).data("product-id"));
        const qty = Number($('input[name="product_qty"]').val());

        if (!product_id || qty <= 0) return;

        $(".website-loader").fadeIn("slow");

        const data = await rpc("/shop/cart/update_json", {
            line_id: false,
            product_id,
            set_qty: qty,
        });

        if (data.cart_quantity > 0) {
            $(".my_cart_quantity").text(data.cart_quantity);
        } else if (data.warning) {
            Dialog.alert(this, _t(data.warning));
        }

        $(".website-loader").fadeOut("slow");
    },

    _clickTermSearch(ev) {
        ev.preventDefault();

        const input = $(ev.currentTarget)
            .parent()
            .find('input[type="search"]');

        this.term = input.val() || "";
        this.offset = 0;

        this.load_quick_shop_products().then(() => this.renderElement());
    },

    _clickViewType(ev) {
        ev.preventDefault();
        this.view_type = $(ev.currentTarget).data("view-type");
        this.renderElement();
    },

    _clickQuickShopFilter(ev) {
        ev.preventDefault();

        this.active_filter = $(ev.currentTarget).data("filter");

        this.load_quick_shop_products().then(() => this.renderElement());
    },

    async load_quick_shop_products() {
        console.log("Fetching quick shop products...");

        const result = await rpc("/fetch_quick_shop_products", {
            term: this.term,
            limit: this.limit,
            offset: this.offset,
            active_filter: this.active_filter,
        });

        if (result?.success) this.data = result;
    },
});

export default publicWidget.registry.QuickShopTemplate;