import logging
import secrets
import select
import socket
import threading

logger = logging.getLogger(__name__)


class DirectTcpProxyManager:
    """
    Manages raw TCP proxy listeners for native VNC clients.

    Each active proxy maps:
        manager_local_port -> node_host:node_vnc_port
    """

    def __init__(self, app=None):
        self._proxies = {}   # vm_name -> {local_port, server_sock, stop_event, thread}
        self._lock = threading.Lock()
        self._port_min = 57000
        self._port_max = 57099
        if app:
            self.init_app(app)

    def init_app(self, app):
        self._app = app
        self._port_min = app.config.get('VNC_DIRECT_PORT_MIN', 57000)
        self._port_max = app.config.get('VNC_DIRECT_PORT_MAX', 57099)

    def _find_free_local_port(self):
        with self._lock:
            used = {info['local_port'] for info in self._proxies.values()}
        for port in range(self._port_min, self._port_max + 1):
            if port in used:
                continue
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                    probe.bind(('0.0.0.0', port))
                    return port
            except OSError:
                continue
        raise RuntimeError('No free direct TCP proxy ports available')

    def start_proxy(self, vm_name, target_host, target_port):
        """
        Start (or reuse) a local TCP proxy for vm_name.
        Returns the allocated local port.
        """
        with self._lock:
            existing = self._proxies.get(vm_name)
            if existing:
                return existing['local_port']

        local_port = self._find_free_local_port()
        stop_event = threading.Event()

        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(('0.0.0.0', local_port))
        server_sock.listen(32)
        server_sock.settimeout(1)

        def _forward():
            try:
                while not stop_event.is_set():
                    try:
                        client_sock, _ = server_sock.accept()
                    except socket.timeout:
                        continue
                    except OSError:
                        # Listener was closed during shutdown.
                        break

                    try:
                        target_sock = socket.create_connection((target_host, target_port), timeout=5)
                    except Exception as e:
                        logger.warning(
                            'Direct proxy connect failed vm=%s target=%s:%s error=%s',
                            vm_name,
                            target_host,
                            target_port,
                            e,
                        )
                        client_sock.close()
                        continue

                    threading.Thread(
                        target=self._bridge,
                        args=(vm_name, client_sock, target_sock),
                        daemon=True,
                    ).start()
            except Exception as e:
                logger.error('Direct proxy listener error vm=%s: %s', vm_name, e)
            finally:
                try:
                    server_sock.close()
                except Exception:
                    pass

        t = threading.Thread(target=_forward, daemon=True)
        t.start()

        with self._lock:
            self._proxies[vm_name] = {
                'local_port': local_port,
                'server_sock': server_sock,
                'stop_event': stop_event,
                'thread': t,
            }

        logger.info(
            'Direct TCP proxy started vm=%s listen=0.0.0.0:%d target=%s:%d',
            vm_name,
            local_port,
            target_host,
            target_port,
        )
        return local_port

    def _record_direct_vnc_session_start(self, vm_name):
        """Record a direct TCP (.vncloc) VNC session start for usage analytics."""
        app = getattr(self, '_app', None)
        if not app:
            return None
        try:
            with app.app_context():
                from app.models import VM
                from app.usage_events import start_vnc_session
                from app.extensions import db

                vm = VM.query.filter_by(name=vm_name).first()
                if not vm or vm.status != 'running':
                    return None
                session_token = secrets.token_urlsafe(24)
                start_vnc_session(vm, session_token=session_token)
                db.session.commit()
                return session_token
        except Exception as e:
            logger.warning('Failed to record direct VNC session start vm=%s: %s', vm_name, e)
            return None

    def _record_direct_vnc_session_end(self, session_token):
        """Record a direct TCP (.vncloc) VNC session end for usage analytics."""
        if not session_token:
            return
        app = getattr(self, '_app', None)
        if not app:
            return
        try:
            with app.app_context():
                from app.usage_events import close_vnc_session
                from app.extensions import db

                close_vnc_session(
                    session_token=session_token,
                    disconnect_reason='direct_tcp_closed',
                )
                db.session.commit()
        except Exception as e:
            logger.warning('Failed to record direct VNC session end: %s', e)

    def _bridge(self, vm_name, client_sock, target_sock):
        session_token = None
        try:
            # Record VNC session for usage analytics (direct TCP .vncloc path)
            session_token = self._record_direct_vnc_session_start(vm_name)

            while True:
                readable, _, _ = select.select([client_sock, target_sock], [], [], 1)
                if client_sock in readable:
                    data = client_sock.recv(65536)
                    if not data:
                        break
                    target_sock.sendall(data)
                if target_sock in readable:
                    data = target_sock.recv(65536)
                    if not data:
                        break
                    client_sock.sendall(data)
        except Exception as e:
            logger.debug('Direct proxy bridge closed vm=%s: %s', vm_name, e)
        finally:
            self._record_direct_vnc_session_end(session_token)
            try:
                target_sock.close()
            except Exception:
                pass
            try:
                client_sock.close()
            except Exception:
                pass

    def stop_proxy(self, vm_name):
        with self._lock:
            info = self._proxies.pop(vm_name, None)
        if not info:
            return
        info['stop_event'].set()
        try:
            info['server_sock'].close()
        except Exception:
            pass
        logger.info('Direct TCP proxy stopped vm=%s', vm_name)

    def get_proxy_port(self, vm_name):
        with self._lock:
            info = self._proxies.get(vm_name)
            return info['local_port'] if info else None

    def cleanup_all(self):
        with self._lock:
            names = list(self._proxies.keys())
        for vm_name in names:
            self.stop_proxy(vm_name)
        logger.info('All direct TCP proxies cleaned up')
