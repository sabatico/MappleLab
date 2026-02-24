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
    const overlayTitle = document.getElementById('global-loading-overlay-title');
    const overlayDetail = document.getElementById('global-loading-overlay-detail');

    let pendingRequests = 0;
    const trackedHtmxRequests = new WeakSet();

    const isOverlayLocked = () => overlay.dataset.locked === '1';
    const showOverlay = () => overlay.classList.remove('d-none');
    const hideOverlay = () => {
        if (isOverlayLocked()) return;
        overlay.classList.add('d-none');
    };
    const beginPending = () => {
        pendingRequests += 1;
        showOverlay();
    };
    const setOverlayMessage = (title, detail) => {
        if (overlayTitle) {
            overlayTitle.textContent = title || 'Loading...';
        }
        if (overlayDetail) {
            overlayDetail.textContent = detail || '';
        }
    };

    const clearOverlayMessage = () => setOverlayMessage('Loading...', '');

    const endPending = () => {
        pendingRequests = Math.max(0, pendingRequests - 1);
        if (pendingRequests === 0) hideOverlay();
    };

    const shouldIgnoreHtmxOverlay = (evt) => {
        const detail = evt && evt.detail ? evt.detail : {};
        const elt = detail.elt;
        if (!(elt instanceof Element)) return false;
        const trigger = (elt.getAttribute('hx-trigger') || '').toLowerCase();
        // Dashboard table body auto-polls every 5s; avoid global flicker.
        return trigger.includes('every') && window.location.pathname === '/';
    };

    const getHtmxXhr = (evt) => {
        return evt && evt.detail ? evt.detail.xhr : null;
    };

    // Expose a page-level overlay lock for long-running workflows (e.g., VM migrate).
    window.setGlobalOverlayLock = (locked) => {
        overlay.dataset.locked = locked ? '1' : '0';
        if (locked) {
            showOverlay();
        } else if (pendingRequests === 0) {
            overlay.classList.add('d-none');
            clearOverlayMessage();
        }
    };
    window.setGlobalOverlayMessage = (title, detail) => setOverlayMessage(title, detail);

    // Show overlay for full-page form submissions.
    // Use bubbling so inline onsubmit handlers (confirm dialogs) run first.
    document.addEventListener('submit', (evt) => {
        const form = evt.target;
        if (!(form instanceof HTMLFormElement)) return;
        if (form.hasAttribute('data-no-loading-overlay')) return;
        if (evt.defaultPrevented) return;
        beginPending();
    });

    // Show overlay for normal page navigation link clicks.
    document.addEventListener('click', (evt) => {
        if (evt.defaultPrevented) return;
        if (evt.button !== 0) return;
        if (evt.metaKey || evt.ctrlKey || evt.shiftKey || evt.altKey) return;
        const link = evt.target.closest('a');
        if (!link) return;
        if (link.target === '_blank') return;
        if (link.hasAttribute('download')) return;
        if (link.classList.contains('vnc-download-link')) return;  // handled separately
        const href = link.getAttribute('href') || '';
        if (!href || href.startsWith('#') || href.startsWith('javascript:')) return;
        if (link.hasAttribute('data-no-loading-overlay')) return;
        beginPending();
    });

    // VNC download links: show overlay until fetch completes, then trigger download and hide.
    document.addEventListener('click', async (evt) => {
        if (evt.defaultPrevented) return;
        if (evt.button !== 0) return;
        if (evt.metaKey || evt.ctrlKey || evt.shiftKey || evt.altKey) return;
        const link = evt.target.closest('a.vnc-download-link');
        if (!link) return;
        const href = link.getAttribute('href') || '';
        if (!href || href.startsWith('#') || href.startsWith('javascript:')) return;

        evt.preventDefault();
        beginPending();
        setOverlayMessage('Preparing download...', '');

        try {
            const resp = await fetch(href, { credentials: 'same-origin' });
            if (!resp.ok) throw new Error(resp.statusText);
            const blob = await resp.blob();
            const cd = resp.headers.get('Content-Disposition') || '';
            const m = cd.match(/filename="?([^";\n]+)"?/);
            const ext = link.dataset.downloadExt || 'vnc';
            const filename = m ? m[1].trim() : `connection.${ext}`;
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            a.style.display = 'none';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (err) {
            console.warn('VNC download failed:', err);
            window.location.href = href;  // fallback to normal navigation
        } finally {
            endPending();
        }
    });

    // HTMX requests should also trigger the same centralized loading overlay.
    document.body.addEventListener('htmx:beforeRequest', (evt) => {
        if (shouldIgnoreHtmxOverlay(evt)) return;
        const xhr = getHtmxXhr(evt);
        if (xhr) trackedHtmxRequests.add(xhr);
        beginPending();
    });
    const endTrackedHtmxOverlay = (evt) => {
        const xhr = getHtmxXhr(evt);
        if (xhr && !trackedHtmxRequests.has(xhr)) return;
        if (xhr) trackedHtmxRequests.delete(xhr);
        endPending();
    };
    document.body.addEventListener('htmx:afterRequest', endTrackedHtmxOverlay);
    document.body.addEventListener('htmx:responseError', endTrackedHtmxOverlay);
    document.body.addEventListener('htmx:sendError', endTrackedHtmxOverlay);

    // Ensure overlay clears if page becomes visible again from bfcache/navigation.
    window.addEventListener('pageshow', () => {
        pendingRequests = 0;
        overlay.dataset.locked = '0';
        hideOverlay();
    });
});

document.body.addEventListener('htmx:responseError', (evt) => {
    console.warn('HTMX request failed:', evt.detail);
});
