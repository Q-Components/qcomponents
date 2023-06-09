odoo.define('hide_checkout', function (require) {
   'use strict';

   var t = require('website_sale.utils')

   t.updateCartNavBar = function updateCartNavBar(data) {
      var $qtyNavBar = $(".my_cart_quantity");
      _.each($qtyNavBar, function (qty) {
         var $qty = $(qty);
         $qty.parents('li:first').removeClass('d-none');
         $qty.html(data.cart_quantity).hide().fadeIn(600);
      });
      $(".js_cart_lines").first().before(data['website_sale.cart_lines']).end().remove();
      $(".js_cart_summary").first().before(data['website_sale.short_cart_summary']).end().remove();

      //***** Custom Data*****
      var res = data['website_sale.check']
      if (res) {
         $('.checkout_one').removeClass("disabled")
         $('#message').addClass("d-none")
      }
      else {
         $('.checkout_one').addClass("disabled")
         $('#message').removeClass("d-none")
      }
      // *******
      
   }
})







