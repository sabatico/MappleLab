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

    const overlay = document.getElementById('global-loading-overlay');
    if (!overlay) return;

    let pendingRequests = 0;

    const showOverlay = () => overlay.classList.remove('d-none');
    const hideOverlay = () => overlay.classList.add('d-none');
    const beginPending = () => {
        pendingRequests += 1;
        showOverlay();
    };
    const endPending = () => {
        pendingRequests = Math.max(0, pendingRequests - 1);
        if (pendingRequests === 0) hideOverlay();
    };

    // Show overlay for full-page form submissions.
    document.addEventListener('submit', (evt) => {
        const form = evt.target;
        if (!(form instanceof HTMLFormElement)) return;
        if (form.hasAttribute('data-no-loading-overlay')) return;
        beginPending();
    }, true);

    // Show overlay for normal page navigation link clicks.
    document.addEventListener('click', (evt) => {
        const link = evt.target.closest('a');
        if (!link) return;
        if (link.target === '_blank') return;
        if (link.hasAttribute('download')) return;
        const href = link.getAttribute('href') || '';
        if (!href || href.startsWith('#') || href.startsWith('javascript:')) return;
        if (link.hasAttribute('data-no-loading-overlay')) return;
        beginPending();
    }, true);

    // HTMX requests should also trigger the same centralized loading overlay.
    document.body.addEventListener('htmx:beforeRequest', beginPending);
    document.body.addEventListener('htmx:afterRequest', endPending);
    document.body.addEventListener('htmx:responseError', endPending);
    document.body.addEventListener('htmx:sendError', endPending);

    // Ensure overlay clears if page becomes visible again from bfcache/navigation.
    window.addEventListener('pageshow', () => {
        pendingRequests = 0;
        hideOverlay();
    });
});

document.body.addEventListener('htmx:responseError', (evt) => {
    console.warn('HTMX request failed:', evt.detail);
});
