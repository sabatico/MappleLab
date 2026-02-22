import logging
import socket
import threading
import time
from flask import render_template, redirect, url_for, flash, current_app, request
from flask_login import login_required, current_user
from app.console import bp
from app.models import VM
from app.tart_client import TartAPIError
from app.extensions import sock

logger = logging.getLogger(__name__)


def _connect_local_tunnel(local_port, retries=8, delay=0.15):
    """Best-effort connect to local tunnel listener with short retries."""
    last_error = None
    for _ in range(retries):
        try:
            return socket.create_connection(('127.0.0.1', local_port), timeout=2)
        except OSError as e:
            last_error = e
            time.sleep(delay)
    raise last_error or RuntimeError('Failed to connect local tunnel')


@bp.route('/<vm_name>')
@login_required
def vnc(vm_name):
    """
    VNC console page for a VM.

    Flow:
    1. Verify VM is running and owned by current user
    2. Ask agent to start websockify on the remote node
    3. Open SSH tunnel from Flask server to agent's websockify port
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
        remote_port = current_app.tart.start_vnc(node, vm_name)
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

    # Open SSH tunnel: Flask local port → node's websockify port
    try:
        local_port = current_app.tunnel_manager.start_tunnel(vm_name, node, remote_port)
        logger.info("vnc() — SSH tunnel on local port %d -> %s:%d", local_port, node.host, remote_port)
    except Exception as e:
        logger.error("vnc() — failed to create SSH tunnel: %s", e)
        flash(f'Failed to create VNC tunnel: {e}', 'danger')
        return redirect(url_for('main.vm_detail', vm_name=vm_name))

    return render_template(
        'console/vnc.html',
        vm_name=vm_name,
        vm=vm,
        ws_path=f'/console/ws/{vm_name}',
        vnc_username=current_app.config['VNC_DEFAULT_USERNAME'],
        vnc_password=current_app.config['VNC_DEFAULT_PASSWORD'],
    )


@bp.route('/<vm_name>/disconnect', methods=['POST'])
@login_required
def disconnect(vm_name):
    """Close the SSH tunnel and stop websockify on the agent."""
    logger.info("disconnect() — vm=%r user=%s", vm_name, current_user.username)

    current_app.tunnel_manager.stop_tunnel(vm_name)

    vm = VM.query.filter_by(name=vm_name, user_id=current_user.id).first()
    if vm and vm.node:
        try:
            current_app.tart.stop_vnc(vm.node, vm_name)
        except TartAPIError:
            pass  # non-critical

    flash('Console disconnected.', 'info')
    return redirect(url_for('main.vm_detail', vm_name=vm_name))


@sock.route('/console/ws/<vm_name>')
def console_ws(ws, vm_name):
    """Same-origin websocket bridge: browser <-> local SSH tunnel socket."""
    if not current_user.is_authenticated:
        ws.close()
        return

    vm = VM.query.filter_by(name=vm_name, user_id=current_user.id).first()
    if not vm or vm.status != 'running':
        ws.close()
        return

    local_port = current_app.tunnel_manager.get_tunnel_port(vm_name)
    if not local_port:
        ws.close()
        return

    try:
        tunnel_sock = _connect_local_tunnel(local_port)
    except Exception as e:
        logger.warning("console_ws(%s) failed to reach local tunnel %s: %s", vm_name, local_port, e)
        ws.close()
        return

    closed = threading.Event()

    def _ws_to_tcp():
        try:
            while not closed.is_set():
                message = ws.receive()
                if message is None:
                    break
                if isinstance(message, str):
                    message = message.encode()
                tunnel_sock.sendall(message)
        except Exception:
            pass
        finally:
            closed.set()
            try:
                tunnel_sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass

    t = threading.Thread(target=_ws_to_tcp, daemon=True)
    t.start()

    try:
        while not closed.is_set():
            data = tunnel_sock.recv(4096)
            if not data:
                break
            ws.send(data)
    except Exception:
        pass
    finally:
        closed.set()
        try:
            tunnel_sock.close()
        except Exception:
            pass
        try:
            ws.close()
        except Exception:
            pass
