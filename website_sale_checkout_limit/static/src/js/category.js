/** @odoo-module **/

import websiteSaleUtils from '@website_sale/js/website_sale_utils';

const originalUpdateCartNavBar = websiteSaleUtils.updateCartNavBar;

websiteSaleUtils.updateCartNavBar = function (data) {

    originalUpdateCartNavBar.apply(this, arguments);
    
    const res = data['website_sale.check'];

    if (res) {
        document.querySelectorAll('.checkout_one').forEach(el => {
            el.classList.remove("disabled");
        });
        document.getElementById('message')?.classList.add("d-none");
    } else {
        document.querySelectorAll('.checkout_one').forEach(el => {
            el.classList.add("disabled");
        });
        document.getElementById('message')?.classList.remove("d-none");
    }
};