odoo.define('algolia_search', function (require) {
    'use strict';
    var publicWidget = require('web.public.widget');
	var rpc = require('web.rpc');
    var websiteId = $('html')[0].dataset.websiteId;

publicWidget.registry.searchBarAlgolia = publicWidget.Widget.extend({
    selector: '.algolia',
    events: {
        'focusout': '_onFocusOut',
        'focusin': '_onFocusIn',
    },
    
    init: function () {
        this._super.apply(this, arguments);
        this._onFocusOut = _.debounce(this._onFocusOut, 100);
    },

    _onFocusOut: function () {
        if (!this.$el.has(document.activeElement).length) {
            $('.aa-dropdown-menu').removeClass("show");
        }
    },

    _onFocusIn: function () {
        $('.aa-dropdown-menu').addClass("show");
    },

    start: function () {
        rpc.query({
            route: "/algolia_search/api",
            params: {
                website_id: websiteId,
            }
        }).then(function (result) {
            if (result['enable_alogolia_search']) {
            let lastRenderArgs;
            const infiniteHits = instantsearch.connectors.connectInfiniteHits(
            (renderArgs, isFirstRender) => {
                const { hits, showMore, widgetParams } = renderArgs;
                const { container } = widgetParams;
    
                lastRenderArgs = renderArgs;
    
                if (isFirstRender) {
                const sentinel = document.createElement('div');
                const newdiv = document.createElement('div');
                newdiv.classList.add('dropdown-menu');
                newdiv.classList.add('aa-dropdown-menu');
                newdiv.classList.add('aloglia-dropdown');
                container.appendChild(sentinel);
                container.appendChild(newdiv);
    
                const observer = new IntersectionObserver(entries => {
                    entries.forEach(entry => {
                        $('.aloglia-dropdown').scroll(function() {
                            if (($('.aloglia-dropdown').prop('scrollTop')/$('.aloglia-dropdown').prop('scrollHeight'))*100 > 65){
                                showMore();
                            }
                          });
                    });
                });
    
                observer.observe(newdiv);
    
                return;
                }

                container.querySelector('.aloglia-dropdown').innerHTML = hits
                .map((hit) => {
                    var list_price = ``;
                            var price = ``;
                            if (hit['currency_position'] == 'after'){
                                list_price += `${hit['list_price']} ${hit['currency']}`;
                                price += `${hit['price']} ${hit['currency']}`;
                            } else {
                                list_price += `${hit['currency']} ${hit['list_price']}`;
                                price += `${hit['currency']} ${hit['price']}`;
                            }
    
                            var discounted = ``;
                            if (hit['has_discounted_price']){
                                discounted  += `
                                    <span class="text-danger text-nowrap" style="text-decoration: line-through;">
                                        ${list_price}
                                    </span>
                                    <b class="text-nowrap">
                                        ${price}
                                    </b>
                                `
                            } else {
                                discounted  += `
                                    <h6 class="font-weight-bold">${list_price}</h6>
                                `
                            }
                        
                            return `
                            <a href="${hit['product_url']}" class="as-dropdown-item as-alg-search-item o_search_product_item text-decoration-none">
                                <div class="as-alg-search-img">
                                    <img src=${hit['src_image']} class="flex-shrink-0 w-100 o_image_256_contain"/>
                                </div>
                                <div class="as-alg-search-text">
                                    <h6 class="font-weight-bold">${hit['name']}</h6>
                                    <div class="as-alg-search-price">
                                        ${discounted}
                                    </div>
                                </div>
                            </a>
                            `
                }
                )
                .join('');
            }
            );
            const searchClient = algoliasearch(result['app_id'],result['search_key']);
    
              const search = instantsearch({
                indexName: result['name'],
                searchClient,
              });
              
              search.addWidgets([
                instantsearch.widgets.searchBox({
                    placeholder: 'Search for products',
                    container: '.algolia',
                }),
                infiniteHits({
                  container: document.querySelector('.algolia'),
                }),
              ]);
              search.start();
            }
        });
        return this._super.apply(this, arguments);
    }
    });
 
    publicWidget.registry.productsSearchBar.include({
		init: function() {
			this._super.apply(this, arguments);
			var child = {focus: function() { }};
			var children = {first: () => child, last: () => child};
			this.$menu = {children: () => children, remove: () => {}};
		},
	});
})