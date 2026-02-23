import unittest
from datetime import datetime, timedelta

from app.admin.usage_metrics import (
    _format_duration,
    _running_and_stopped,
    _running_vnc_seconds,
)


class _Session:
    def __init__(self, connected_at, disconnected_at=None):
        self.connected_at = connected_at
        self.disconnected_at = disconnected_at


class UsageMetricsMathTests(unittest.TestCase):
    def test_format_duration(self):
        self.assertEqual(_format_duration(60), '1m')
        self.assertEqual(_format_duration(3660), '1h 1m')
        self.assertEqual(_format_duration(90061), '1d 1h 1m')

    def test_running_and_stopped_splits_intervals(self):
        start = datetime(2026, 1, 1, 10, 0, 0)
        intervals = [
            (start, start + timedelta(minutes=30), 'stopped'),
            (start + timedelta(minutes=30), start + timedelta(hours=2), 'running'),
            (start + timedelta(hours=2), start + timedelta(hours=3), 'failed'),
        ]
        running_seconds, stopped_seconds, running_intervals = _running_and_stopped(intervals)
        self.assertEqual(stopped_seconds, 30 * 60)
        self.assertEqual(running_seconds, 90 * 60)
        self.assertEqual(len(running_intervals), 1)

    def test_running_vnc_intersection(self):
        start = datetime(2026, 1, 1, 8, 0, 0)
        running_intervals = [
            (start, start + timedelta(hours=2)),
            (start + timedelta(hours=3), start + timedelta(hours=4)),
        ]
        sessions = [
            _Session(start + timedelta(minutes=30), start + timedelta(hours=1, minutes=30)),
            _Session(start + timedelta(hours=1, minutes=45), start + timedelta(hours=3, minutes=30)),
        ]
        total = _running_vnc_seconds(
            running_intervals=running_intervals,
            sessions=sessions,
            now=start + timedelta(hours=5),
        )
        # overlaps: 60m + 15m + 30m = 105m
        self.assertEqual(total, 105 * 60)


if __name__ == '__main__':
    unittest.main()
