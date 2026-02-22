import logging
from app.tart_client import TartClient, TartAPIError

logger = logging.getLogger(__name__)


def _normalize_registry_url(registry_url):
    """
    Normalize registry host for OCI tags.
    Tart expects host[:port] without http(s) scheme.
    """
    value = (registry_url or '').strip().rstrip('/')
    if value.startswith('http://'):
        value = value[len('http://'):]
    elif value.startswith('https://'):
        value = value[len('https://'):]
    return value


class NodeManager:
    """
    High-level VM scheduling across TART nodes.
    Selects which node to run a VM on, checks capacity, etc.
    """

    def __init__(self, app=None):
        self._client = None
        if app:
            self.init_app(app)

    def init_app(self, app):
        self._client = TartClient(app)
        # Expose raw TartClient on app as well
        app.tart = self._client

    def find_best_node(self):
        """Return the active Node with the most free VM slots, or None."""
        from app.models import Node
        nodes = Node.query.filter_by(active=True).all()
        best = None
        best_free = 0
        for node in nodes:
            try:
                health = self._client.get_health(node)
                free = health.get('free_slots', 0)
                if free > best_free:
                    best = node
                    best_free = free
            except TartAPIError as e:
                logger.warning('Node %s health check failed: %s', node.name, e)
        return best

    def get_all_nodes_health(self):
        """Return list of (node, health_dict | None) tuples for all active nodes."""
        from app.models import Node
        nodes = Node.query.filter_by(active=True).all()
        result = []
        for node in nodes:
            try:
                health = self._client.get_health(node)
                result.append((node, health))
            except TartAPIError:
                result.append((node, None))
        return result

    def registry_tag_for(self, username, vm_name, registry_url):
        """Build the full OCI registry path for a VM."""
        base = _normalize_registry_url(registry_url)
        return f'{base}/{username}/{vm_name}:latest'
