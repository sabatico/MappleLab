/**
 * console.js — noVNC integration for Orchard UI.
 *
 * Imports RFB from the locally-hosted noVNC core library.
 * Config is injected from Flask via window.VNC_CONFIG.
 */

import RFB from '/static/novnc/core/rfb.js';
import { initLogging } from '/static/novnc/core/util/logging.js';

const { wsPath, directWsUrl, vncUsername, password, vmName } = window.VNC_CONFIG;

const indicator = document.getElementById('status-indicator');
const overlay = document.getElementById('disconnect-overlay');
const overlayMessage = document.getElementById('disconnect-message');
const profileBandwidthBtn = document.getElementById('profile-bandwidth');
const profileRenderBtn = document.getElementById('profile-render');

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
const wsUrl = directWsUrl || `${wsScheme}://${window.location.host}${wsPath}`;

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

const VNC_PROFILES = {
    bandwidth: {
        scaleViewport: true,
        resizeSession: true,
        clipViewport: true,
        qualityLevel: 1,
        compressionLevel: 9,
        showDotCursor: true,
    },
    render: {
        scaleViewport: true,
        resizeSession: false,
        clipViewport: false,
        qualityLevel: 2,
        compressionLevel: 6,
        showDotCursor: true,
    },
};

function applyProfile(name) {
    const profile = VNC_PROFILES[name];
    if (!profile) return;

    rfb.scaleViewport = profile.scaleViewport;
    rfb.resizeSession = profile.resizeSession;
    rfb.clipViewport = profile.clipViewport;
    rfb.qualityLevel = profile.qualityLevel;
    rfb.compressionLevel = profile.compressionLevel;
    rfb.showDotCursor = profile.showDotCursor;

    profileBandwidthBtn?.classList.toggle('active', name === 'bandwidth');
    profileRenderBtn?.classList.toggle('active', name === 'render');
    console.log(`Applied VNC profile "${name}"`, profile);
}

applyProfile('bandwidth');

profileBandwidthBtn?.addEventListener('click', () => applyProfile('bandwidth'));
profileRenderBtn?.addEventListener('click', () => applyProfile('render'));

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
