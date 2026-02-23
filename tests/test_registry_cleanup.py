import unittest
from unittest.mock import patch

from flask import Flask

from app.registry_cleanup import (
    cleanup_tag,
    parse_registry_tag,
    resolve_manifest_digest,
)


class _MockResponse:
    def __init__(self, status_code=200, headers=None):
        self.status_code = status_code
        self.headers = headers or {}

    @property
    def ok(self):
        return 200 <= self.status_code < 300


class RegistryCleanupTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['REGISTRY_URL'] = 'http://127.0.0.1:5001'
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def test_parse_registry_tag_plain(self):
        parsed = parse_registry_tag('192.168.1.195:5001/admin/11:latest')
        self.assertEqual(parsed['host'], '192.168.1.195:5001')
        self.assertEqual(parsed['repo'], 'admin/11')
        self.assertEqual(parsed['tag'], 'latest')

    def test_parse_registry_tag_http_v2(self):
        parsed = parse_registry_tag('http://192.168.1.195:5001/v2/admin/11:latest')
        self.assertEqual(parsed['host'], '192.168.1.195:5001')
        self.assertEqual(parsed['repo'], 'admin/11')
        self.assertEqual(parsed['tag'], 'latest')

    @patch('app.registry_cleanup.requests.request')
    def test_resolve_digest_head_success(self, mock_request):
        mock_request.return_value = _MockResponse(
            status_code=200,
            headers={'Docker-Content-Digest': 'sha256:abc'},
        )
        res = resolve_manifest_digest('192.168.1.195:5001/admin/11:latest')
        self.assertTrue(res['ok'])
        self.assertFalse(res['missing'])
        self.assertEqual(res['digest'], 'sha256:abc')

    @patch('app.registry_cleanup.requests.request')
    def test_resolve_digest_missing_manifest(self, mock_request):
        mock_request.return_value = _MockResponse(status_code=404)
        res = resolve_manifest_digest('192.168.1.195:5001/admin/11:latest')
        self.assertTrue(res['ok'])
        self.assertTrue(res['missing'])
        self.assertIsNone(res['digest'])

    @patch('app.registry_cleanup.requests.request')
    def test_cleanup_tag_delete_500(self, mock_request):
        # HEAD succeeds with digest, DELETE fails with 500.
        responses = [
            _MockResponse(status_code=200, headers={'Docker-Content-Digest': 'sha256:deadbeef'}),
            _MockResponse(status_code=500),
            _MockResponse(status_code=500),
            _MockResponse(status_code=500),
        ]
        mock_request.side_effect = responses
        res = cleanup_tag('192.168.1.195:5001/admin/11:latest')
        self.assertFalse(res['ok'])
        self.assertEqual(res['digest'], 'sha256:deadbeef')
        self.assertEqual(res['status_code'], 500)
        self.assertIn('DELETE manifest failed', res['error'])

    @patch('app.registry_cleanup.time.sleep')
    @patch('app.registry_cleanup.requests.request')
    def test_cleanup_tag_retries_delete_5xx(self, mock_request, mock_sleep):
        # HEAD success, DELETE returns 500 then 202.
        responses = [
            _MockResponse(status_code=200, headers={'Docker-Content-Digest': 'sha256:ok'}),
            _MockResponse(status_code=500),
            _MockResponse(status_code=202),
        ]
        mock_request.side_effect = responses
        res = cleanup_tag('192.168.1.195:5001/admin/11:latest')
        self.assertTrue(res['ok'])
        self.assertEqual(res['status_code'], 202)
        self.assertGreaterEqual(mock_sleep.call_count, 1)


if __name__ == '__main__':
    unittest.main()
