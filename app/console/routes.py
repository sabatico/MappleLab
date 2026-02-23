import logging
import threading
import time
from flask import render_template, redirect, url_for, flash, current_app, request
from flask_login import login_required, current_user
from simple_websocket.errors import ConnectionClosed
from app.console import bp
from app.models import VM
from app.tart_client import TartAPIError
from app.extensions import sock
import websocket

logger = logging.getLogger(__name__)

# When SSH tunnel is off, store node host:port per VM for the WS bridge.
_vnc_direct_targets = {}   # vm_name → (node_host, websockify_port)


def _connect_backend_ws(url, retries=8, delay=0.15):
    """Best-effort websocket connect to backend (local tunnel or remote node)."""
    last_error = None
    for _ in range(retries):
        try:
            return websocket.create_connection(
                url,
                timeout=5,
                enable_multithread=True,
            )
        except Exception as e:
            last_error = e
            time.sleep(delay)
    raise last_error or RuntimeError(f'Failed to connect backend WS: {url}')


@bp.route('/<vm_name>')
@login_required
def vnc(vm_name):
    """
    VNC console page for a VM.

    Flow:
    1. Verify VM is running and owned by current user
    2. Ask agent to start websockify on the remote node
    3. If VNC_USE_SSH_TUNNEL: open SSH tunnel to node's websockify port
       Otherwise: record node host:port for direct WS from the bridge
    4. Render noVNC page with WebSocket connection info
    """
    logger.info("vnc() — opening console for VM %r (user=%s)", vm_name, current_user.username)

    vm = VM.query.filter_by(name=vm_name, user_id=current_user.id).first_or_404()

    if vm.status != 'running':
        flash(f'VM "{vm_name}" is not running (status: {vm.status}).', 'warning')
        return redirect(url_for('main.vm_detail', vm_name=vm_name))

    host = request.host.split(':')[0]
    if not request.is_secure and host not in ('localhost', '127.0.0.1'):
        flash(
            'Remote console access requires HTTPS to enable browser cryptography for '
            'Apple VNC authentication. Open the manager UI via https:// and retry.',
            'warning',
        )
        return redirect(url_for('main.vm_detail', vm_name=vm_name))

    node = vm.node
    if not node:
        flash(f'VM "{vm_name}" has no assigned node.', 'danger')
        return redirect(url_for('main.vm_detail', vm_name=vm_name))

    # Ask agent to start websockify on the remote node
    try:
        remote_port, _vnc_port = current_app.tart.start_vnc(node, vm_name)
        logger.debug("vnc() — agent started websockify on port %d", remote_port)
    except TartAPIError as e:
        logger.error("vnc() — failed to start VNC on agent: %s", e)
        msg = str(e)
        if (
            'No reachable VNC endpoint' in msg
            or 'localhost VNC is unavailable' in msg
            or '127.0.0.1:5900' in msg
        ):
            flash(
                'No VNC endpoint is currently reachable for this VM. '
                'Verify the VM is running, then restart it from the UI Start button '
                '(launches Tart with --vnc) and retry Console.',
                'warning',
            )
        else:
            flash(f'Failed to start VNC on node: {e}', 'danger')
        return redirect(url_for('main.vm_detail', vm_name=vm_name))

    use_ssh = current_app.config.get('VNC_USE_SSH_TUNNEL', False)
    use_browser_direct = current_app.config.get('VNC_BROWSER_DIRECT_NODE_WS', False)
    direct_ws_url = None

    if use_browser_direct:
        configured_scheme = current_app.config.get('VNC_BROWSER_DIRECT_NODE_WS_SCHEME', '').strip()
        direct_scheme = configured_scheme or ('wss' if request.is_secure else 'ws')
        direct_ws_url = f'{direct_scheme}://{node.host}:{remote_port}'
        # Ensure stale relay routes are not used when browser-direct mode is enabled.
        _vnc_direct_targets.pop(vm_name, None)
        current_app.tunnel_manager.stop_tunnel(vm_name)
        logger.info("vnc() — browser direct websocket enabled: %s", direct_ws_url)
    elif use_ssh:
        try:
            local_port = current_app.tunnel_manager.start_tunnel(vm_name, node, remote_port)
            logger.info("vnc() — SSH tunnel on local port %d -> %s:%d", local_port, node.host, remote_port)
        except Exception as e:
            logger.error("vnc() — failed to create SSH tunnel: %s", e)
            flash(f'Failed to create VNC tunnel: {e}', 'danger')
            return redirect(url_for('main.vm_detail', vm_name=vm_name))
    else:
        _vnc_direct_targets[vm_name] = (node.host, remote_port)
        logger.info("vnc() — direct WS to %s:%d (no SSH tunnel)", node.host, remote_port)

    return render_template(
        'console/vnc.html',
        vm_name=vm_name,
        vm=vm,
        ws_path=f'/console/ws/{vm_name}',
        direct_ws_url=direct_ws_url,
        vnc_username=current_app.config['VNC_DEFAULT_USERNAME'],
        vnc_password=current_app.config['VNC_DEFAULT_PASSWORD'],
    )


@bp.route('/<vm_name>/disconnect', methods=['POST'])
@login_required
def disconnect(vm_name):
    """Close the SSH tunnel (if any) and stop websockify on the agent."""
    logger.info("disconnect() — vm=%r user=%s", vm_name, current_user.username)

    current_app.tunnel_manager.stop_tunnel(vm_name)
    current_app.direct_tcp_proxy.stop_proxy(vm_name)
    _vnc_direct_targets.pop(vm_name, None)

    vm = VM.query.filter_by(name=vm_name, user_id=current_user.id).first()
    if vm and vm.node:
        try:
            current_app.tart.stop_vnc(vm.node, vm_name)
        except TartAPIError:
            pass  # non-critical

    flash('Console disconnected.', 'info')
    return redirect(url_for('main.vm_detail', vm_name=vm_name))


@bp.route('/<vm_name>/vncloc')
@login_required
def download_vncloc(vm_name):
    """Download a macOS Screen Sharing (.vncloc) file for direct TCP VNC."""
    vm = VM.query.filter_by(name=vm_name, user_id=current_user.id).first_or_404()
    if vm.status != 'running':
        flash(f'VM "{vm_name}" must be running to download a connection file.', 'warning')
        return redirect(url_for('main.vm_detail', vm_name=vm_name))
    if not vm.node:
        flash(f'VM "{vm_name}" has no assigned node.', 'danger')
        return redirect(url_for('main.vm_detail', vm_name=vm_name))

    try:
        _ws_port, vnc_port = current_app.tart.start_vnc(vm.node, vm_name)
    except TartAPIError as e:
        flash(f'Failed to prepare VNC endpoint: {e}', 'danger')
        return redirect(url_for('main.vm_detail', vm_name=vm_name))

    # Native VNC clients require raw RFB/TCP to VM VNC, not node websockify WS.
    # Use VM IP as the direct proxy target.
    vm_ip = current_app.tart.get_vm_ip(vm.node, vm_name)
    if not vm_ip:
        flash(f'Could not determine VM IP for "{vm_name}".', 'danger')
        return redirect(url_for('main.vm_detail', vm_name=vm_name))

    try:
        proxy_port = current_app.direct_tcp_proxy.start_proxy(
            vm_name,
            vm_ip,
            vnc_port,
        )
    except Exception as e:
        logger.error(
            "download_vncloc(%s) failed to start direct proxy to %s:%s: %s",
            vm_name,
            vm_ip,
            vnc_port,
            e,
        )
        flash(f'Failed to prepare direct TCP proxy: {e}', 'danger')
        return redirect(url_for('main.vm_detail', vm_name=vm_name))

    manager_host = request.host.split(':', 1)[0]
    vnc_url = f'vnc://{manager_host}:{proxy_port}'
    vncloc_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        f'  <key>URL</key><string>{vnc_url}</string>\n'
        '</dict></plist>\n'
    )
    filename = f'{vm_name}.vncloc'
    return current_app.response_class(
        vncloc_xml,
        mimetype='application/octet-stream',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@sock.route('/console/ws/<vm_name>')
def console_ws(ws, vm_name):
    """Same-origin websocket bridge: browser <-> backend websockify."""
    session_started = time.monotonic()
    logger.info("console_ws(%s) opened websocket request", vm_name)
    try:
        if not current_user.is_authenticated:
            logger.info("console_ws(%s) closing: unauthenticated websocket", vm_name)
            ws.close()
            return

        vm = VM.query.filter_by(name=vm_name, user_id=current_user.id).first()
        if not vm or vm.status != 'running':
            logger.info(
                "console_ws(%s) closing: vm missing or not running (vm=%s status=%s)",
                vm_name,
                bool(vm),
                vm.status if vm else None,
            )
            ws.close()
            return

        direct = _vnc_direct_targets.get(vm_name)
        if direct:
            node_host, node_port = direct
            backend_url = f"ws://{node_host}:{node_port}"
        else:
            local_port = current_app.tunnel_manager.get_tunnel_port(vm_name)
            if not local_port:
                logger.info("console_ws(%s) closing: no backend route found", vm_name)
                ws.close()
                return
            backend_url = f"ws://127.0.0.1:{local_port}"

        logger.info("console_ws(%s) connecting backend %s", vm_name, backend_url)

        try:
            backend_connect_started = time.monotonic()
            tunnel_ws = _connect_backend_ws(backend_url)
            backend_connect_ms = int((time.monotonic() - backend_connect_started) * 1000)
            logger.info(
                "console_ws(%s) backend websocket connected in %dms",
                vm_name,
                backend_connect_ms,
            )
        except Exception as e:
            logger.warning("console_ws(%s) failed to reach backend %s: %s", vm_name, backend_url, e)
            ws.close()
            return

        closed = threading.Event()
        ws_send_lock = threading.Lock()
        metrics_lock = threading.Lock()
        metrics = {
            'browser_to_tunnel_frames': 0,
            'browser_to_tunnel_bytes': 0,
            'tunnel_to_browser_frames': 0,
            'tunnel_to_browser_bytes': 0,
            'backend_recv_timeouts': 0,
            'first_browser_to_tunnel_ms': None,
            'first_tunnel_to_browser_ms': None,
        }

        def _ws_to_tcp():
            try:
                while not closed.is_set():
                    message = ws.receive()
                    # simple-websocket can return None for non-data frames / keepalive.
                    # Do not treat this as a disconnect by itself.
                    if message is None:
                        time.sleep(0.01)
                        continue
                    if isinstance(message, str):
                        tunnel_ws.send(message)
                        payload_len = len(message.encode('utf-8'))
                    else:
                        tunnel_ws.send(message, opcode=websocket.ABNF.OPCODE_BINARY)
                        payload_len = len(message)
                    with metrics_lock:
                        metrics['browser_to_tunnel_frames'] += 1
                        metrics['browser_to_tunnel_bytes'] += payload_len
                        if metrics['first_browser_to_tunnel_ms'] is None:
                            metrics['first_browser_to_tunnel_ms'] = int(
                                (time.monotonic() - session_started) * 1000
                            )
                            logger.info(
                                "console_ws(%s) first browser->tunnel frame forwarded at %dms",
                                vm_name,
                                metrics['first_browser_to_tunnel_ms'],
                            )
            except ConnectionClosed as e:
                logger.info(
                    "console_ws(%s) browser websocket closed (code=%s, reason=%s)",
                    vm_name,
                    e.reason,
                    e.message,
                )
            except Exception:
                logger.exception("console_ws(%s) browser->tunnel bridge error", vm_name)
            finally:
                closed.set()
                try:
                    tunnel_ws.close()
                except Exception:
                    pass

        t = threading.Thread(target=_ws_to_tcp, daemon=True)
        t.start()

        last_ping_ts = time.time()
        try:
            while not closed.is_set():
                try:
                    data = tunnel_ws.recv()
                except websocket.WebSocketTimeoutException:
                    with metrics_lock:
                        metrics['backend_recv_timeouts'] += 1
                    now = time.time()
                    if now - last_ping_ts >= 30:
                        try:
                            tunnel_ws.ping()
                        except Exception:
                            logger.warning("console_ws(%s) backend WS ping failed, closing", vm_name)
                            break
                        last_ping_ts = now
                    continue
                if data is None:
                    logger.info("console_ws(%s) tunnel closed by remote endpoint", vm_name)
                    break
                try:
                    with ws_send_lock:
                        ws.send(data)
                except ConnectionClosed as e:
                    logger.info(
                        "console_ws(%s) browser websocket closed during send (code=%s, reason=%s)",
                        vm_name,
                        e.reason,
                        e.message,
                    )
                    break
                payload_len = len(data.encode('utf-8')) if isinstance(data, str) else len(data)
                with metrics_lock:
                    metrics['tunnel_to_browser_frames'] += 1
                    metrics['tunnel_to_browser_bytes'] += payload_len
                    if metrics['first_tunnel_to_browser_ms'] is None:
                        metrics['first_tunnel_to_browser_ms'] = int(
                            (time.monotonic() - session_started) * 1000
                        )
                        logger.info(
                            "console_ws(%s) first tunnel->browser frame forwarded at %dms",
                            vm_name,
                            metrics['first_tunnel_to_browser_ms'],
                        )
        except Exception:
            logger.exception("console_ws(%s) tunnel->browser bridge error", vm_name)
        finally:
            closed.set()
            try:
                tunnel_ws.close()
            except Exception:
                pass
            session_ms = int((time.monotonic() - session_started) * 1000)
            with metrics_lock:
                logger.info(
                    "console_ws(%s) session summary: duration_ms=%d backend=%s "
                    "tx_frames=%d tx_bytes=%d rx_frames=%d rx_bytes=%d "
                    "first_tx_ms=%s first_rx_ms=%s backend_timeouts=%d",
                    vm_name,
                    session_ms,
                    backend_url,
                    metrics['browser_to_tunnel_frames'],
                    metrics['browser_to_tunnel_bytes'],
                    metrics['tunnel_to_browser_frames'],
                    metrics['tunnel_to_browser_bytes'],
                    metrics['first_browser_to_tunnel_ms'],
                    metrics['first_tunnel_to_browser_ms'],
                    metrics['backend_recv_timeouts'],
                )

        try:
            with ws_send_lock:
                ws.close()
        except ConnectionClosed:
            # Normal case if browser already closed.
            pass
        except Exception:
            logger.exception("console_ws(%s) websocket close error", vm_name)
    except Exception:
        logger.exception("console_ws(%s) unexpected bridge error", vm_name)
        try:
            with ws_send_lock:
                ws.close()
        except ConnectionClosed:
            pass
        except Exception:
            pass
