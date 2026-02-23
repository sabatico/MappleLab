import logging
import time
from urllib.parse import urlparse

import requests

from app.node_manager import _sanitize_registry_repo_segment
from app.registry_cleanup import delete_manifest

logger = logging.getLogger(__name__)

_MANIFEST_ACCEPT = ', '.join([
    'application/vnd.oci.image.manifest.v1+json',
    'application/vnd.oci.image.index.v1+json',
    'application/vnd.docker.distribution.manifest.v2+json',
    'application/vnd.docker.distribution.manifest.list.v2+json',
])


def _trim_error(text, limit=220):
    value = (text or '').strip()
    if len(value) <= limit:
        return value
    return f'{value[:limit - 3]}...'


def _registry_base_and_host(registry_url):
    value = (registry_url or '').strip()
    if not value:
        return 'http://localhost:5001', 'localhost:5001'
    if value.startswith(('http://', 'https://')):
        parsed = urlparse(value)
        scheme = parsed.scheme or 'http'
        host = parsed.netloc
    else:
        scheme = 'http'
        parsed = urlparse(f'//{value}')
        host = parsed.netloc or value.split('/', 1)[0]
    return f'{scheme}://{host}', host


def registry_host(registry_url):
    _, host = _registry_base_and_host(registry_url)
    return host


def _request_with_retry(method, url, *, headers=None, timeout=8, attempts=3):
    last_exc = None
    last_resp = None
    for attempt in range(attempts):
        try:
            resp = requests.request(method, url, headers=headers, timeout=timeout)
            if resp.status_code < 500 or attempt == attempts - 1:
                return resp, None
            sleep_for = 0.5 * (2 ** attempt)
            logger.warning(
                'registry_inventory %s %s got %s, retrying in %.1fs (%s/%s)',
                method, url, resp.status_code, sleep_for, attempt + 1, attempts,
            )
            last_resp = resp
            time.sleep(sleep_for)
        except requests.RequestException as e:
            last_exc = e
            if attempt == attempts - 1:
                break
            sleep_for = 0.5 * (2 ** attempt)
            logger.warning(
                'registry_inventory %s %s request error=%s, retrying in %.1fs (%s/%s)',
                method, url, _trim_error(str(e), 120), sleep_for, attempt + 1, attempts,
            )
            time.sleep(sleep_for)
    if last_resp is not None:
        return last_resp, None
    return None, last_exc


def _manifest_size_bytes(payload):
    if not isinstance(payload, dict):
        return 0
    total = 0
    config = payload.get('config') or {}
    if isinstance(config, dict):
        total += int(config.get('size') or 0)
    layers = payload.get('layers') or []
    if isinstance(layers, list):
        for layer in layers:
            if isinstance(layer, dict):
                total += int(layer.get('size') or 0)
    manifests = payload.get('manifests') or []
    if isinstance(manifests, list):
        for manifest in manifests:
            if isinstance(manifest, dict):
                total += int(manifest.get('size') or 0)
    return total


def _list_catalog(base_url):
    url = f'{base_url}/v2/_catalog'
    resp, err = _request_with_retry('GET', url)
    if err is not None:
        raise RuntimeError(f'catalog request failed: {err}')
    if not resp.ok:
        raise RuntimeError(f'catalog request failed status={resp.status_code}')
    data = resp.json() if resp.content else {}
    repos = data.get('repositories') or []
    return [repo for repo in repos if isinstance(repo, str) and repo.strip()]


def _list_tags(base_url, repo):
    url = f'{base_url}/v2/{repo}/tags/list'
    resp, err = _request_with_retry('GET', url)
    if err is not None:
        logger.warning('registry_inventory list tags failed repo=%s error=%s', repo, err)
        return []
    if resp.status_code == 404:
        return []
    if not resp.ok:
        logger.warning('registry_inventory list tags failed repo=%s status=%s', repo, resp.status_code)
        return []
    data = resp.json() if resp.content else {}
    tags = data.get('tags') or []
    return [tag for tag in tags if isinstance(tag, str) and tag.strip()]


def _manifest_info(base_url, repo, tag):
    url = f'{base_url}/v2/{repo}/manifests/{tag}'
    headers = {'Accept': _MANIFEST_ACCEPT}
    resp, err = _request_with_retry('GET', url, headers=headers)
    if err is not None:
        logger.warning('registry_inventory manifest read failed repo=%s tag=%s error=%s', repo, tag, err)
        return {'ok': False, 'error': _trim_error(str(err))}
    if not resp.ok:
        return {'ok': False, 'error': f'manifest read failed status={resp.status_code}'}
    digest = (resp.headers.get('Docker-Content-Digest') or '').strip() or None
    try:
        payload = resp.json() if resp.content else {}
    except ValueError:
        payload = {}
    size_bytes = _manifest_size_bytes(payload)
    return {'ok': True, 'digest': digest, 'size_bytes': size_bytes}


def list_registry_items(registry_url):
    """
    Return registry artefacts as rows:
      {repo, tag, registry_tag, digest, size_gb}
    """
    base_url, host = _registry_base_and_host(registry_url)
    rows = []
    for repo in _list_catalog(base_url):
        for tag in _list_tags(base_url, repo):
            info = _manifest_info(base_url, repo, tag)
            rows.append({
                'repo': repo,
                'tag': tag,
                'registry_tag': f'{host}/{repo}:{tag}',
                'digest': info.get('digest'),
                'size_gb': round((info.get('size_bytes') or 0) / (1024 ** 3), 2),
                'error': info.get('error'),
            })
    return rows


def _vm_lookup_by_sanitized_user_vm():
    from app.models import User, VM

    lookup = {}
    users = {u.id: u for u in User.query.all()}
    for vm in VM.query.all():
        user = users.get(vm.user_id)
        if not user:
            continue
        key = (
            _sanitize_registry_repo_segment(user.username),
            _sanitize_registry_repo_segment(vm.name),
        )
        lookup.setdefault(key, []).append((user, vm))
    return lookup


def classify_registry_items(registry_url):
    """
    Classify registry inventory into trackable and orphaned based on SQL linkage.
    """
    items = list_registry_items(registry_url)
    lookup = _vm_lookup_by_sanitized_user_vm()
    trackable = []
    orphaned = []

    for item in items:
        repo = item.get('repo') or ''
        parts = [p for p in repo.split('/') if p]
        if len(parts) < 2:
            item['orphan_reason'] = 'Repository path has no user/vm namespace'
            orphaned.append(item)
            continue
        namespace = parts[0]
        image = parts[-1]
        matched = lookup.get((namespace, image), [])
        if matched:
            # Prefer records that are likely lifecycle-relevant for stored artefacts.
            priority = {'archived': 0, 'pushing': 1, 'pulling': 2, 'failed': 3}
            matched.sort(key=lambda pair: priority.get(pair[1].status, 99))
            user, vm = matched[0]
            enriched = dict(item)
            enriched.update({
                'user_email': user.email or user.username,
                'user_name': user.username,
                'vm_name': vm.name,
                'vm_status': vm.status,
                'vm_id': vm.id,
                'cleanup_status': vm.cleanup_status,
                'cleanup_last_error': vm.cleanup_last_error,
            })
            trackable.append(enriched)
        else:
            orphan = dict(item)
            orphan['orphan_reason'] = (
                'No matching VM found in SQL by sanitized user/vm path '
                f'({namespace}/{image})'
            )
            orphaned.append(orphan)
    return trackable, orphaned


def storage_breakdown(registry_url, configured_total_gb=None):
    trackable, orphaned = classify_registry_items(registry_url)
    trackable_used_gb = round(sum(i.get('size_gb') or 0 for i in trackable), 2)
    orphaned_used_gb = round(sum(i.get('size_gb') or 0 for i in orphaned), 2)
    used_gb = round(trackable_used_gb + orphaned_used_gb, 2)
    total_gb = configured_total_gb if configured_total_gb is not None else None
    free_gb = round(max((total_gb or 0) - used_gb, 0), 2) if total_gb is not None else None
    return {
        'trackable': trackable,
        'orphaned': orphaned,
        'trackable_used_gb': trackable_used_gb,
        'orphaned_used_gb': orphaned_used_gb,
        'used_gb': used_gb,
        'total_gb': total_gb,
        'free_gb': free_gb,
    }


def delete_orphan_by_digest(registry_url, repo, digest):
    if not repo or not digest:
        return {'ok': False, 'error': 'Missing repo or digest', 'status_code': None}
    return delete_manifest(registry_host(registry_url), repo, digest)

