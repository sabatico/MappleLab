/**
 * console.js — noVNC integration for Orchard UI.
 *
 * Imports RFB from the locally-hosted noVNC core library.
 * Config is injected from Flask via window.VNC_CONFIG.
 */

import RFB from '/static/novnc/core/rfb.js';

const { wsHost, wsPort, password, vmName } = window.VNC_CONFIG;

const indicator = document.getElementById('status-indicator');
const overlay = document.getElementById('disconnect-overlay');
const overlayMessage = document.getElementById('disconnect-message');

function setStatus(state) {
    indicator.className = '';
    indicator.classList.add(state);
}

function showOverlay(message) {
    overlayMessage.textContent = message || 'Connection Lost';
    overlay.classList.add('visible');
}

function hideOverlay() {
    overlay.classList.remove('visible');
}

setStatus('connecting');

const wsUrl = `ws://${wsHost}:${wsPort}`;

const rfb = new RFB(
    document.getElementById('vnc-container'),
    wsUrl,
    {
        credentials: { password },
        shared: true,
    }
);

rfb.scaleViewport = true;
rfb.resizeSession = false;
rfb.clipViewport = false;

rfb.addEventListener('connect', () => {
    setStatus('connected');
    hideOverlay();
    console.log(`noVNC connected to ${vmName}`);
});

rfb.addEventListener('disconnect', (evt) => {
    setStatus('disconnected');
    if (evt.detail?.clean) {
        console.log(`noVNC disconnected cleanly from ${vmName}`);
        showOverlay('VNC session ended.');
    } else {
        const reason = evt.detail?.reason || 'Connection lost unexpectedly.';
        console.warn(`noVNC disconnected from ${vmName}:`, reason);
        showOverlay(reason);
    }
});

rfb.addEventListener('credentialsrequired', () => {
    rfb.sendCredentials({ password });
});

rfb.addEventListener('securityfailure', (evt) => {
    setStatus('disconnected');
    showOverlay(`Security failure: ${evt.detail?.reason || 'wrong password?'}`);
});
