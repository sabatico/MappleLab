import logging
import select
import socket
import threading

import paramiko

logger = logging.getLogger(__name__)


class TunnelManager:
    """
    Manages SSH port-forward tunnels from the Flask server to TART agent nodes.

    Each active VNC console gets one tunnel:
        Flask local port → remote node's websockify port → VM VNC :5900

    Thread-safe. Replaces WebsockifyManager for VNC proxying.
    """

    def __init__(self, app=None):
        self._tunnels = {}   # vm_name → {local_port, ssh_client, stop_event, thread}
        self._lock = threading.Lock()
        self._port_min = 6900
        self._port_max = 6999
        if app:
            self.init_app(app)

    def init_app(self, app):
        self._port_min = app.config.get('WEBSOCKIFY_PORT_MIN', 6900)
        self._port_max = app.config.get('WEBSOCKIFY_PORT_MAX', 6999)

    # ── Port allocation ────────────────────────────────────────────────────────

    def _find_free_local_port(self):
        with self._lock:
            used = {info['local_port'] for info in self._tunnels.values()}
        for port in range(self._port_min, self._port_max + 1):
            if port in used:
                continue
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('0.0.0.0', port))
                    return port
            except OSError:
                continue
        raise RuntimeError('No free tunnel ports available')

    # ── Tunnel lifecycle ───────────────────────────────────────────────────────

    def start_tunnel(self, vm_name, node, remote_port):
        """
        Open an SSH tunnel: localhost:<local_port> → node:<remote_port>

        Returns the local port number for the browser WebSocket connection.
        If a tunnel already exists for this vm_name, returns its port immediately.
        """
        with self._lock:
            if vm_name in self._tunnels:
                return self._tunnels[vm_name]['local_port']

        local_port = self._find_free_local_port()

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            node.host,
            username=node.ssh_user,
            key_filename=node.ssh_key_path,
            timeout=10,
        )

        transport = ssh.get_transport()
        if transport:
            # Keep SSH transport alive to reduce idle disconnects.
            transport.set_keepalive(20)
        stop_event = threading.Event()

        def _forward():
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                server.bind(('0.0.0.0', local_port))
                server.listen(5)
                server.settimeout(1)
                while not stop_event.is_set():
                    try:
                        client_sock, _ = server.accept()
                    except socket.timeout:
                        continue
                    try:
                        chan = transport.open_channel(
                            'direct-tcpip',
                            # Connect from the node to its own local listener.
                            # Using localhost is more reliable than node LAN IP.
                            ('127.0.0.1', remote_port),
                            ('localhost', local_port),
                        )
                    except Exception as e:
                        logger.error(
                            'Failed to open SSH channel for %s to 127.0.0.1:%d: %s',
                            vm_name, remote_port, e,
                        )
                        client_sock.close()
                        continue
                    threading.Thread(
                        target=_bridge, args=(client_sock, chan), daemon=True
                    ).start()
            except Exception as e:
                logger.error('Tunnel listener error for %s: %s', vm_name, e)
            finally:
                server.close()

        def _bridge(sock, chan):
            try:
                while True:
                    r, _, _ = select.select([sock, chan], [], [], 1)
                    if sock in r:
                        data = sock.recv(4096)
                        if not data:
                            break
                        chan.send(data)
                    if chan in r:
                        data = chan.recv(4096)
                        if not data:
                            break
                        sock.send(data)
            except Exception:
                pass
            finally:
                chan.close()
                sock.close()

        t = threading.Thread(target=_forward, daemon=True)
        t.start()

        with self._lock:
            self._tunnels[vm_name] = {
                'local_port': local_port,
                'ssh_client': ssh,
                'stop_event': stop_event,
                'thread': t,
            }

        logger.info(
            'SSH tunnel started: localhost:%d → %s:%d (%s)',
            local_port, node.host, remote_port, vm_name,
        )
        return local_port

    def stop_tunnel(self, vm_name):
        with self._lock:
            info = self._tunnels.pop(vm_name, None)
        if info is None:
            return
        info['stop_event'].set()
        info['ssh_client'].close()
        logger.info('SSH tunnel stopped for %s', vm_name)

    def get_tunnel_port(self, vm_name):
        with self._lock:
            info = self._tunnels.get(vm_name)
            return info['local_port'] if info else None

    def cleanup_all(self):
        with self._lock:
            names = list(self._tunnels.keys())
        for name in names:
            self.stop_tunnel(name)
        logger.info('All SSH tunnels cleaned up')
