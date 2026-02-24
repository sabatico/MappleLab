import logging
import requests

logger = logging.getLogger(__name__)


class TartAPIError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class TartClient:
    """
    HTTP client for the TART Agent API.
    Each Flask app has one instance; pass a Node object to each call
    so the client knows which agent endpoint to reach.
    """

    def __init__(self, app=None):
        self._token = ''
        if app:
            self.init_app(app)

    def init_app(self, app):
        self._token = app.config.get('AGENT_TOKEN', '')

    def _headers(self):
        h = {}
        if self._token:
            h['Authorization'] = f'Bearer {self._token}'
        return h

    def _request(self, method, node, path, **kwargs):
        url = f'{node.agent_url}{path}'
        kwargs.setdefault('timeout', 30)
        try:
            resp = requests.request(method, url, headers=self._headers(), **kwargs)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            raise TartAPIError(
                f'Cannot connect to TART agent on {node.host}:{node.agent_port}'
            )
        except requests.exceptions.Timeout:
            raise TartAPIError(f'TART agent request timed out: {method} {path}')
        except requests.exceptions.HTTPError as e:
            msg = str(e)
            try:
                body = e.response.json()
                if isinstance(body, dict) and body.get('error'):
                    msg = body['error']
            except Exception:
                pass
            raise TartAPIError(msg, status_code=e.response.status_code)

    # ── Node health ────────────────────────────────────────────────────────────

    def get_health(self, node):
        return self._request('GET', node, '/health')

    # ── VM operations ──────────────────────────────────────────────────────────

    def list_vms(self, node):
        return self._request('GET', node, '/vms')

    def create_vm(self, node, name, base_image, cpu=None, memory_mb=None):
        return self._request('POST', node, '/vms/create', json={
            'name': name,
            'base_image': base_image,
            'cpu': cpu,
            'memory_mb': memory_mb,
        })

    def start_vm(self, node, name):
        return self._request('POST', node, f'/vms/{name}/start')

    def stop_vm(self, node, name):
        return self._request('POST', node, f'/vms/{name}/stop')

    def save_vm(self, node, name, registry_tag, expected_disk_gb=None):
        """Triggers async save on agent. Poll get_op_status for progress."""
        payload = {'registry_tag': registry_tag}
        if expected_disk_gb is not None:
            payload['expected_disk_gb'] = expected_disk_gb
        return self._request('POST', node, f'/vms/{name}/save', json=payload)

    def restore_vm(self, node, name, registry_tag, expected_disk_gb=None):
        """Triggers async restore on agent. Poll get_op_status for progress."""
        payload = {'registry_tag': registry_tag}
        if expected_disk_gb is not None:
            payload['expected_disk_gb'] = expected_disk_gb
        return self._request('POST', node, f'/vms/{name}/restore', json=payload)

    def get_op_status(self, node, name):
        """Poll in-progress async operation status."""
        return self._request('GET', node, f'/vms/{name}/op')

    def get_vm_ip(self, node, name):
        result = self._request('GET', node, f'/vms/{name}/ip')
        return result.get('ip')

    def delete_vm(self, node, name):
        return self._request('DELETE', node, f'/vms/{name}')

    # ── VNC ───────────────────────────────────────────────────────────────────

    def start_vnc(self, node, name):
        result = self._request('POST', node, f'/vnc/{name}/start')
        ws_port = result.get('port')
        # Backwards-compatible fallback for older agents that only return
        # websockify port and assume VM VNC on 5900.
        vnc_port = result.get('vnc_port') or 5900
        return ws_port, vnc_port

    def stop_vnc(self, node, name):
        return self._request('POST', node, f'/vnc/{name}/stop')
