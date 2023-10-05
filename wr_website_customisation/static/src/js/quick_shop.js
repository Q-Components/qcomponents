odoo.define('wr_website_customisation.quick_shop', function(require) {
'use strict';

    var ajax = require('web.ajax');
	var Widget = require('web.Widget');
	var Dialog = require('web.Dialog');
	var rpc = require('web.rpc');
	var core = require('web.core');

	var QWeb = core.qweb;
	var _t = core._t;

    var QuickShopTemplate = Widget.extend({
        template: 'QuickShopTemplate',
        events: {
            'click .pagination-prev-btn':'_clickPaginationPrevButton',
            'click .pagination-next-btn':'_clickPaginationNextButton',
            'keyup input[type="search"]': '_keyupSearchProduct',
            'click a.js_decrease_qty': '_clickDecreaseQty',
            'click a.js_increase_qty': '_clickIncreaseQty',
            'click a.add_to_cart': '_clickAddToCart',
            'click button.term_search_btn': '_clickTermSearch',
        },
        init: function(parent, options){
            this.data = [];
            this.term = '';
            this.limit = 20;
            this.offset = 0;
            this._super.apply(this, arguments);
        },
        willStart: function(){
        	return $.when(this.load_quick_shop_products());
        },
        start: function(){
            return this._super.apply(this, arguments).then(function(){
                $(".website-loader").fadeOut("slow");
                $('[type="search"]').focus();
            });
        },
        load_quick_shop_products: function(){
            var self = this;
            return rpc.query({
                route: '/fetch_quick_shop_products',
                params: {
                    'term': this.term,
                    'limit': this.limit,
                    'offset': this.offset,
                }
            }).then(function(result){
                if(result && result.success){
                    self.data = result;
                }
            });
        },
        _clickPaginationPrevButton: function(ev){
            ev.preventDefault();
            var self = this;
            if(this.data && this.data.current_offset > 1){
                this.offset = (this.data.current_offset - 1) - this.limit;
            }
            this.load_quick_shop_products().then(function(){
                self.renderElement();
            });
        },
        _clickPaginationNextButton: function(ev){
            var self = this;
            ev.preventDefault();
            if(this.data && this.data.next_offset <= this.data.max_offset){
                this.offset = this.data.next_offset;
            }
            this.load_quick_shop_products().then(function(){
                self.renderElement();
            });
        },
        _keyupSearchProduct: function(ev){
            var self = this;
            ev.preventDefault();
            if(ev.keyCode === 13){
                if($(ev.currentTarget).val().length <= 0){
                    this.term = '';
                }else{
                    this.term = $(ev.currentTarget).val();
                }
                this.offset = 0;
                this.load_quick_shop_products().then(function(){
                    self.renderElement();
                });
            }
        },
        _clickIncreaseQty: function(ev){
            ev.preventDefault();
            $('input[name="product_qty"]').val(Number($('input[name="product_qty"]').val() || 0) + 1);
        },
        _clickDecreaseQty: function(ev){
            ev.preventDefault();
            if(Number($('input[name="product_qty"]').val()) > 0) {
                $('input[name="product_qty"]').val(Number($('input[name="product_qty"]').val() || 0) - 1);
            }
        },
        _clickAddToCart: function(ev){
            ev.preventDefault();
            var self = this;
            var product_id = Number($(ev.currentTarget).data('product-id'));
            var value = Number($('input[name="product_qty"]').val());
            if(product_id && value > 0){
                $(".website-loader").fadeIn("slow");
                rpc.query({
                    route: "/shop/cart/update_json",
                    params: {
                        line_id: false,
                        product_id: product_id,
                        set_qty: value
                    },
                }).then(function (data) {
                    if(data.cart_quantity > 0){
                        $('.my_cart_quantity').text(data.cart_quantity);
                    }else{
                        if(data.warning){
                            Dialog.alert(self, _t(data.warning));
                        }
                    }
                    $(".website-loader").fadeOut("slow");
                });
            }
        },
        _clickTermSearch: function(ev){
            var self = this;
            ev.preventDefault();
            if($(ev.currentTarget).parent().find('input[type="search"]').val().length <= 0){
                this.term = '';
            }else{
                this.term = $(ev.currentTarget).parent().find('input[type="search"]').val();
            }
            this.offset = 0;
            this.load_quick_shop_products().then(function(){
                self.renderElement();
            });
        }
	});

	$(document).ready(function(){
	    if(location.pathname == '/quick/shop'){
            var $elem = $('.oe_quick_shop_view');
            var quick_shop_view = new QuickShopTemplate(null, $elem);
            quick_shop_view.appendTo($elem);
	    }
    });

});