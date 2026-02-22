/**
 * console.js — noVNC integration for Orchard UI.
 *
 * Imports RFB from the locally-hosted noVNC core library.
 * Config is injected from Flask via window.VNC_CONFIG.
 */

import RFB from '/static/novnc/core/rfb.js';
import { initLogging } from '/static/novnc/core/util/logging.js';

const { wsPath, vncUsername, password, vmName } = window.VNC_CONFIG;

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
const sessionStart = performance.now();

const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
const wsUrl = `${wsScheme}://${window.location.host}${wsPath}`;

initLogging('warn');

const rfb = new RFB(
    document.getElementById('vnc-container'),
    wsUrl,
    {
        credentials: { username: vncUsername, password },
        // Apple VNC behaves better with an exclusive session.
        shared: false,
    }
);

rfb.scaleViewport = true;
rfb.resizeSession = true;
rfb.clipViewport = true;
// Fast profile: lowest usable quality + strongest compression.
rfb.qualityLevel = 1;
rfb.compressionLevel = 9;

rfb.addEventListener('connect', () => {
    setStatus('connected');
    hideOverlay();
    console.log(`noVNC connected to ${vmName} in ${Math.round(performance.now() - sessionStart)}ms`);
});

rfb.addEventListener('desktopname', (evt) => {
    console.log(`noVNC desktop name for ${vmName}:`, evt.detail?.name);
});

rfb.addEventListener('disconnect', (evt) => {
    setStatus('disconnected');
    const lifetimeMs = Math.round(performance.now() - sessionStart);
    if (evt.detail?.clean) {
        console.log(`noVNC disconnected cleanly from ${vmName} after ${lifetimeMs}ms`);
        showOverlay('VNC session ended.');
    } else {
        const reason = evt.detail?.reason || 'Connection lost unexpectedly.';
        console.warn(`noVNC disconnected from ${vmName} after ${lifetimeMs}ms:`, reason);
        showOverlay(reason);
    }
});

rfb.addEventListener('credentialsrequired', () => {
    rfb.sendCredentials({ username: vncUsername, password });
});

rfb.addEventListener('securityfailure', (evt) => {
    setStatus('disconnected');
    showOverlay(`Security failure: ${evt.detail?.reason || 'wrong password?'}`);
});
