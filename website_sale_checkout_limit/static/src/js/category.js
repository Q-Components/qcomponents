odoo.define('hide_checkout', function (require) {
   'use strict';

   var t = require('website_sale.utils')

   t.updateCartNavBar = function updateCartNavBar(data) {
       $(".my_cart_quantity")
        .parents('li.o_wsale_my_cart').removeClass('d-none').end()
        .addClass('o_mycart_zoom_animation').delay(300)
        .queue(function () {
            $(this)
                .toggleClass('fa fa-warning', !data.cart_quantity)
                .attr('title', data.warning)
                .text(data.cart_quantity || '')
                .removeClass('o_mycart_zoom_animation')
                .dequeue();
        });

    $(".js_cart_lines").first().before(data['website_sale.cart_lines']).end().remove();
    $(".js_cart_summary").replaceWith(data['website_sale.short_cart_summary']);

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







