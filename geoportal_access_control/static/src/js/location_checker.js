/** @odoo-module **/

import publicWidget from '@web/legacy/js/public/public_widget';
import { rpc } from '@web/core/network/rpc';

/**
 * LocationCheckerWidget checks the user's location and displays warnings
 * if the user is from restricted countries or states.
 */
publicWidget.registry.LocationCheckerWidget = publicWidget.Widget.extend({
    selector: '#wrapwrap',

    /**
     * Initializes the widget and starts the location fetch process.
     * @override
     */
    init() {
        this._super(...arguments);
        this.orm = this.bindService("orm");
        this.notAllowedCountries = []; // List of restricted countries
        this.notAllowedStates = [];    // List of restricted states
        this.warningMsg = '';         // Custom warning message
        this.maxRetries = 5;          // Maximum number of retry attempts
        this.attempt = 0;             // Current attempt count

        this._fetchUserLocation();    // Start fetching user location
    },

    /**
     * Fetches the user's location from an external API and processes the response.
     * Retries up to maxRetries times if the request fails.
     * @private
     */
    _fetchUserLocation() {
        const self = this;

        $.ajax({
            url: 'https://ipinfo.io/json',
            method: 'GET',
            dataType: 'json',
            timeout: 1000,  // 1 seconds timeout
            success(data) {
                console.log('Location data:', data);
                self._processLocationData(data);
            },
            error(jqXHR, textStatus, errorThrown) {
                self.attempt++;

                if (self.attempt < self.maxRetries) {
                    console.warn(`Attempt ${self.attempt} failed. Retrying...`);
                    self._fetchUserLocation();  // Retry fetching location
                } else {
                    const errorMsg = textStatus === 'timeout'
                        ? 'Request timed out after 5 attempts!'
                        : `Error fetching location after 5 attempts: ${errorThrown}`;
                    console.error(errorMsg);
                    self._showError('Unable to retrieve your location after multiple attempts.');
                }
            }
        });
    },

    /**
     * Processes the location data received from the API.
     * Sends the data to the server for further validation.
     * @param {Object} data - The location data from the API.
     * @private
     */
    _processLocationData(data) {
        const self = this;

        rpc('/get_user_location', data).then((result) => {
            result = JSON.parse(result);

            if (result.error) {
                self._showError(result.error);
            } else {
                self.warningMsg = result.custom_msg;
                if (result.not_allowed) {
                    self._showMessage(result.custom_msg);
                }
            }
        }).catch((error) => {
            console.error('RPC Error:', error);
            self._showError('Server error while processing location.');
        });
    },

    /**
     * Displays an error message in the console and shows a generic error message on the UI.
     * @param {string} error - The error message to display.
     * @private
     */
    _showError(error) {
        console.error('Location Error:', error);
        this._showMessage('Unable to retrieve your location.');
    },

    /**
     * Displays a warning message on the screen.
     * @param {string} message - The message to display.
     * @private
     */
    _showMessage(message) {
        this.$el.before(`
                <div class="alert alert-warning d-flex flex-column align-items-center justify-content-center"
                    role="alert"
                    style="
                        position: fixed; 
                        top: 0; 
                        left: 0; 
                        width: 100vw; 
                        height: 100vh; 
                        background-color: #ffc107; 
                        color: #000; 
                        text-align: center; 
                        font-size: 24px; 
                        font-weight: bold; 
                        display: flex;
                        z-index: 9999; /* Ensures this element stays on top */
                    ">
                    <i class="fa fa-exclamation-triangle fa-3x mb-3"></i>
                    <span>${message}</span>
                </div>
            `);
        // Hide the rest of the page content
        $('body').children().not('.alert').css('display', 'none');

    }
});
