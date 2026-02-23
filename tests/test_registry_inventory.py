import unittest
from unittest.mock import patch

from app.registry_inventory import (
    _manifest_size_bytes,
    classify_registry_items,
    storage_breakdown,
)


class RegistryInventoryTests(unittest.TestCase):
    def test_manifest_size_bytes_sums_components(self):
        payload = {
            'config': {'size': 100},
            'layers': [{'size': 200}, {'size': 300}],
            'manifests': [{'size': 400}],
        }
        self.assertEqual(_manifest_size_bytes(payload), 1000)

    @patch('app.registry_inventory._vm_lookup_by_sanitized_user_vm')
    @patch('app.registry_inventory.list_registry_items')
    def test_classify_trackable_and_orphan(self, mock_items, mock_lookup):
        mock_items.return_value = [
            {
                'repo': 'admin/lab1',
                'tag': 'latest',
                'registry_tag': 'r:5001/admin/lab1:latest',
                'digest': 'sha256:1',
                'size_gb': 10.0,
            },
            {
                'repo': 'ghost/missing',
                'tag': 'latest',
                'registry_tag': 'r:5001/ghost/missing:latest',
                'digest': 'sha256:2',
                'size_gb': 5.0,
            },
        ]

        class _User:
            email = 'admin@example.com'
            username = 'admin@example.com'

        class _Vm:
            id = 11
            name = 'lab1'
            status = 'archived'
            cleanup_status = 'done'
            cleanup_last_error = None

        mock_lookup.return_value = {('admin', 'lab1'): [(_User(), _Vm())]}
        trackable, orphaned = classify_registry_items('http://r:5001/v2/')
        self.assertEqual(len(trackable), 1)
        self.assertEqual(trackable[0]['vm_name'], 'lab1')
        self.assertEqual(len(orphaned), 1)
        self.assertIn('No matching VM found', orphaned[0]['orphan_reason'])

    @patch('app.registry_inventory.classify_registry_items')
    def test_storage_breakdown_math(self, mock_classify):
        mock_classify.return_value = (
            [{'size_gb': 10.5}, {'size_gb': 1.5}],
            [{'size_gb': 3.0}],
        )
        result = storage_breakdown('http://r:5001/v2/', configured_total_gb=20)
        self.assertEqual(result['trackable_used_gb'], 12.0)
        self.assertEqual(result['orphaned_used_gb'], 3.0)
        self.assertEqual(result['used_gb'], 15.0)
        self.assertEqual(result['free_gb'], 5.0)


if __name__ == '__main__':
    unittest.main()
