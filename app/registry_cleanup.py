import logging
import time
from datetime import datetime
from urllib.parse import urlparse

import requests
from flask import current_app

logger = logging.getLogger(__name__)

_MANIFEST_ACCEPT = ', '.join([
    'application/vnd.oci.image.manifest.v1+json',
    'application/vnd.oci.image.index.v1+json',
    'application/vnd.docker.distribution.manifest.v2+json',
    'application/vnd.docker.distribution.manifest.list.v2+json',
])


def _trim_error(text, limit=240):
    value = (text or '').strip()
    if len(value) <= limit:
        return value
    return f'{value[:limit - 3]}...'


def parse_registry_tag(registry_tag):
    """
    Parse a registry tag into host/repo/tag.
    Accepts:
      - host:port/repo/name:tag
      - http(s)://host:port/v2/repo/name:tag
    """
    value = (registry_tag or '').strip()
    if not value:
        raise ValueError('registry_tag is empty')

    if value.startswith(('http://', 'https://')):
        parsed = urlparse(value)
        value = f'{parsed.netloc}{parsed.path}'

    value = value.strip('/')
    parts = [p for p in value.split('/') if p]
    if len(parts) < 2:
        raise ValueError(f'invalid registry tag: {registry_tag!r}')

    host = parts[0]
    repo_parts = parts[1:]
    if repo_parts and repo_parts[0].lower() == 'v2':
        repo_parts = repo_parts[1:]
    if not repo_parts:
        raise ValueError(f'invalid registry tag repository: {registry_tag!r}')

    last = repo_parts[-1]
    if ':' in last:
        name, tag = last.rsplit(':', 1)
        repo_parts[-1] = name
    else:
        tag = 'latest'

    repo = '/'.join(repo_parts).strip('/')
    if not repo:
        raise ValueError(f'invalid registry tag repository: {registry_tag!r}')

    return {'host': host, 'repo': repo, 'tag': tag}


def _registry_scheme():
    configured = (current_app.config.get('REGISTRY_URL') or '').strip().lower()
    if configured.startswith('https://'):
        return 'https'
    return 'http'


def _registry_manifest_url(host, repo, reference):
    scheme = _registry_scheme()
    return f'{scheme}://{host}/v2/{repo}/manifests/{reference}'


def _request_with_retry(method, url, *, headers=None, timeout=8, attempts=3):
    """
    Retry transient network failures and 5xx responses with exponential backoff.
    """
    last_exc = None
    last_resp = None
    for attempt in range(attempts):
        try:
            resp = requests.request(method, url, headers=headers, timeout=timeout)
            if resp.status_code < 500 or attempt == attempts - 1:
                return resp, None
            # Retryable 5xx response.
            sleep_for = 0.5 * (2 ** attempt)
            logger.warning(
                'registry_cleanup %s %s got %s, retrying in %.1fs (%s/%s)',
                method,
                url,
                resp.status_code,
                sleep_for,
                attempt + 1,
                attempts,
            )
            last_resp = resp
            time.sleep(sleep_for)
        except requests.RequestException as e:
            last_exc = e
            if attempt == attempts - 1:
                break
            sleep_for = 0.5 * (2 ** attempt)
            logger.warning(
                'registry_cleanup %s %s request error=%s, retrying in %.1fs (%s/%s)',
                method,
                url,
                _trim_error(str(e), 120),
                sleep_for,
                attempt + 1,
                attempts,
            )
            time.sleep(sleep_for)
    if last_resp is not None:
        return last_resp, None
    return None, last_exc


def resolve_manifest_digest(registry_tag, timeout=8):
    parsed = parse_registry_tag(registry_tag)
    url = _registry_manifest_url(parsed['host'], parsed['repo'], parsed['tag'])
    headers = {'Accept': _MANIFEST_ACCEPT}

    # Try HEAD first; some registries omit digest on HEAD, so fallback to GET.
    try:
        head, head_error = _request_with_retry('HEAD', url, headers=headers, timeout=timeout)
        if head_error is not None:
            raise head_error
        digest = (head.headers.get('Docker-Content-Digest') or '').strip()
        if head.status_code == 404:
            return {'ok': True, 'missing': True, 'digest': None, 'status_code': 404}
        if head.ok and digest:
            return {'ok': True, 'missing': False, 'digest': digest, 'status_code': head.status_code}
        if head.status_code not in (405, 400):
            # If HEAD says hard failure, return it without fallback.
            if head.status_code >= 500:
                return {
                    'ok': False,
                    'missing': False,
                    'digest': None,
                    'status_code': head.status_code,
                    'error': f'HEAD manifest failed with {head.status_code}',
                }
    except requests.RequestException as e:
        return {
            'ok': False,
            'missing': False,
            'digest': None,
            'status_code': None,
            'error': _trim_error(str(e)),
        }

    try:
        get_resp, get_error = _request_with_retry('GET', url, headers=headers, timeout=timeout)
        if get_error is not None:
            raise get_error
        digest = (get_resp.headers.get('Docker-Content-Digest') or '').strip()
        if get_resp.status_code == 404:
            return {'ok': True, 'missing': True, 'digest': None, 'status_code': 404}
        if get_resp.ok and digest:
            return {'ok': True, 'missing': False, 'digest': digest, 'status_code': get_resp.status_code}
        return {
            'ok': False,
            'missing': False,
            'digest': None,
            'status_code': get_resp.status_code,
            'error': f'GET manifest did not return digest (status {get_resp.status_code})',
        }
    except requests.RequestException as e:
        return {
            'ok': False,
            'missing': False,
            'digest': None,
            'status_code': None,
            'error': _trim_error(str(e)),
        }


def delete_manifest(host, repo, digest, timeout=8):
    url = _registry_manifest_url(host, repo, digest)
    try:
        resp, req_error = _request_with_retry('DELETE', url, timeout=timeout)
        if req_error is not None:
            raise req_error
        if resp.status_code in (200, 202, 404):
            logger.info(
                'registry_cleanup delete_manifest host=%s repo=%s digest=%s status=%s',
                host, repo, digest, resp.status_code,
            )
            return {'ok': True, 'status_code': resp.status_code}
        if resp.status_code == 405:
            # Common Docker registry behavior when deletion is not enabled.
            msg = (
                'DELETE manifest failed with 405 (method not allowed). '
                'Registry delete may be disabled; set REGISTRY_STORAGE_DELETE_ENABLED=true '
                'for the registry and restart it.'
            )
            logger.warning(
                'registry_cleanup delete_manifest 405 host=%s repo=%s digest=%s body=%s',
                host,
                repo,
                digest,
                _trim_error(getattr(resp, 'text', ''), 240),
            )
            return {'ok': False, 'status_code': resp.status_code, 'error': msg}
        logger.warning(
            'registry_cleanup delete_manifest failed host=%s repo=%s digest=%s status=%s body=%s',
            host,
            repo,
            digest,
            resp.status_code,
            _trim_error(getattr(resp, 'text', ''), 240),
        )
        return {
            'ok': False,
            'status_code': resp.status_code,
            'error': f'DELETE manifest failed with {resp.status_code}',
        }
    except requests.RequestException as e:
        return {'ok': False, 'status_code': None, 'error': _trim_error(str(e))}


def cleanup_tag(registry_tag):
    """
    Resolve tag -> digest -> delete manifest by digest.
    Returns structured result:
      {ok, digest, status_code, error, missing}
    """
    try:
        parsed = parse_registry_tag(registry_tag)
    except ValueError as e:
        return {'ok': False, 'digest': None, 'status_code': None, 'error': str(e), 'missing': False}

    resolved = resolve_manifest_digest(registry_tag)
    if not resolved.get('ok'):
        return {
            'ok': False,
            'digest': None,
            'status_code': resolved.get('status_code'),
            'error': resolved.get('error') or 'Failed to resolve manifest digest',
            'missing': False,
        }
    if resolved.get('missing'):
        return {'ok': True, 'digest': None, 'status_code': 404, 'error': None, 'missing': True}

    digest = resolved.get('digest')
    deleted = delete_manifest(parsed['host'], parsed['repo'], digest)
    return {
        'ok': bool(deleted.get('ok')),
        'digest': digest,
        'status_code': deleted.get('status_code'),
        'error': deleted.get('error'),
        'missing': False,
    }


def cleanup_vm_registry_tag(vm, operation):
    """
    Run best-effort registry cleanup for a VM and persist operational metadata.
    This must not raise into lifecycle handlers.
    """
    try:
        vm.cleanup_last_run_at = datetime.utcnow()
        vm.cleanup_target_digest = None

        tag = (vm.registry_tag or '').strip()
        if not tag:
            vm.cleanup_status = 'done'
            vm.cleanup_last_error = None
            return {'ok': True, 'missing': True, 'digest': None, 'status_code': None, 'error': None}

        result = cleanup_tag(tag)
        vm.cleanup_target_digest = result.get('digest')
        if result.get('ok'):
            vm.cleanup_status = 'done'
            vm.cleanup_last_error = None
            logger.info(
                'registry_cleanup op=%s vm=%s tag=%s digest=%s status_code=%s missing=%s',
                operation,
                vm.name,
                tag,
                result.get('digest'),
                result.get('status_code'),
                result.get('missing', False),
            )
        else:
            vm.cleanup_status = 'warning'
            vm.cleanup_last_error = _trim_error(result.get('error') or 'Unknown cleanup error', 255)
            logger.warning(
                'registry_cleanup op=%s vm=%s tag=%s failed status_code=%s error=%s',
                operation,
                vm.name,
                tag,
                result.get('status_code'),
                vm.cleanup_last_error,
            )
        return result
    except Exception as e:
        vm.cleanup_status = 'warning'
        vm.cleanup_last_error = _trim_error(f'Unexpected cleanup error: {e}', 255)
        logger.exception(
            'registry_cleanup op=%s vm=%s unexpected error',
            operation,
            getattr(vm, 'name', 'unknown'),
        )
        return {'ok': False, 'digest': None, 'status_code': None, 'error': vm.cleanup_last_error, 'missing': False}
