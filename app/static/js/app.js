/**
 * app.js — General dashboard JavaScript.
 *
 * Responsibilities:
 * - Auto-dismiss flash messages after 5 seconds
 * - HTMX event hooks for future enhancements
 *
 * HTMX handles polling automatically via HTML attributes.
 */

document.addEventListener('DOMContentLoaded', () => {
    // Auto-dismiss flash messages after 5 seconds
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            bsAlert.close();
        }, 5000);
    });
});

document.body.addEventListener('htmx:responseError', (evt) => {
    console.warn('HTMX request failed:', evt.detail);
});
