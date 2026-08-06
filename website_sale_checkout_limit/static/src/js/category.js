/** @odoo-module **/

import websiteSaleUtils from '@website_sale/js/website_sale_utils';

const originalUpdateCartNavBar = websiteSaleUtils.updateCartNavBar;

websiteSaleUtils.updateCartNavBar = function (data) {

    originalUpdateCartNavBar.apply(this, arguments);
    
    const res = data['website_sale_check'];
    const expressForm = document.querySelector('form[name="o_payment_express_checkout_form"]');
    if (res) {
        document.querySelectorAll('.checkout_one').forEach(el => {
            el.classList.remove("disabled");
        });
        document.getElementById('message')?.classList.add("d-none");
        expressForm?.classList.remove("d-none");
    } else {
        document.querySelectorAll('.checkout_one').forEach(el => {
            el.classList.add("disabled");
        });
        document.getElementById('message')?.classList.remove("d-none");
        expressForm?.classList.add("d-none");
    }
};