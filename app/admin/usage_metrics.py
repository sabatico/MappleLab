from datetime import datetime
from sqlalchemy.orm import selectinload
from app.extensions import db
from app.models import VM, VMStatusEvent, VMVncSession
from app.usage_events import ensure_vm_status_baseline


def _seconds_between(start, end):
    if not start or not end:
        return 0
    delta = (end - start).total_seconds()
    return int(delta) if delta > 0 else 0


def _format_duration(seconds):
    seconds = max(int(seconds or 0), 0)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _build_state_intervals(vm, now):
    started_at = vm.created_at or now
    rows = sorted(
        vm.status_events or [],
        key=lambda e: (e.changed_at or now, e.id or 0),
    )
    if not rows:
        return started_at, []

    intervals = []
    state = rows[0].to_status or vm.status
    cursor = started_at
    for event in rows[1:]:
        boundary = event.changed_at or now
        if boundary > now:
            boundary = now
        if boundary > cursor:
            intervals.append((cursor, boundary, state))
            cursor = boundary
        state = event.to_status or state
    if now > cursor:
        intervals.append((cursor, now, state))
    return started_at, intervals


def _running_and_stopped(intervals):
    running_seconds = 0
    stopped_seconds = 0
    running_intervals = []
    for start, end, state in intervals:
        duration = _seconds_between(start, end)
        if duration <= 0:
            continue
        if state == 'running':
            running_seconds += duration
            running_intervals.append((start, end))
        elif state == 'stopped':
            stopped_seconds += duration
    return running_seconds, stopped_seconds, running_intervals


def _running_vnc_seconds(running_intervals, sessions, now):
    total = 0
    for session in sessions:
        session_start = session.connected_at
        session_end = session.disconnected_at or now
        if not session_start or session_end <= session_start:
            continue
        for run_start, run_end in running_intervals:
            overlap_start = max(run_start, session_start)
            overlap_end = min(run_end, session_end)
            total += _seconds_between(overlap_start, overlap_end)
    return total


def build_usage_by_user(now=None):
    now = now or datetime.utcnow()
    vms = (
        VM.query
        .options(
            selectinload(VM.owner),
            selectinload(VM.node),
            selectinload(VM.status_events),
            selectinload(VM.vnc_sessions),
        )
        .filter(VM.status.in_(('running', 'stopped')))
        .filter(VM.node_id.isnot(None))
        .order_by(VM.user_id.asc(), VM.name.asc())
        .all()
    )

    for vm in vms:
        ensure_vm_status_baseline(vm, source='system', context='usage_tab_baseline')
    db.session.flush()

    running_warn_seconds = 8 * 3600
    vnc_warn_seconds = 4 * 3600
    by_user = {}

    for vm in vms:
        started_at, intervals = _build_state_intervals(vm, now)
        lifetime_seconds = _seconds_between(started_at, now)
        running_seconds, stopped_seconds, running_intervals = _running_and_stopped(intervals)
        running_vnc_seconds = _running_vnc_seconds(running_intervals, vm.vnc_sessions or [], now)
        running_vnc_seconds = min(running_vnc_seconds, running_seconds)
        running_no_vnc_seconds = max(running_seconds - running_vnc_seconds, 0)

        total_segments = stopped_seconds + running_no_vnc_seconds + running_vnc_seconds
        if total_segments > lifetime_seconds and total_segments > 0:
            scale = lifetime_seconds / float(total_segments)
            stopped_seconds = int(stopped_seconds * scale)
            running_no_vnc_seconds = int(running_no_vnc_seconds * scale)
            running_vnc_seconds = max(lifetime_seconds - stopped_seconds - running_no_vnc_seconds, 0)

        lifetime_safe = max(lifetime_seconds, 1)
        vm_row = {
            'vm': vm,
            'lifetime_seconds': lifetime_seconds,
            'stopped_seconds': stopped_seconds,
            'running_no_vnc_seconds': running_no_vnc_seconds,
            'running_vnc_seconds': running_vnc_seconds,
            'stopped_pct': (stopped_seconds / lifetime_safe) * 100.0,
            'running_no_vnc_pct': (running_no_vnc_seconds / lifetime_safe) * 100.0,
            'running_vnc_pct': (running_vnc_seconds / lifetime_safe) * 100.0,
            'lifetime_display': _format_duration(lifetime_seconds),
            'stopped_display': _format_duration(stopped_seconds),
            'running_no_vnc_display': _format_duration(running_no_vnc_seconds),
            'running_vnc_display': _format_duration(running_vnc_seconds),
            'running_warn': running_no_vnc_seconds >= running_warn_seconds,
            'vnc_warn': running_vnc_seconds >= vnc_warn_seconds,
        }

        user_bucket = by_user.setdefault(
            vm.user_id,
            {
                'user': vm.owner,
                'vms': [],
                'total_lifetime_seconds': 0,
                'total_stopped_seconds': 0,
                'total_running_no_vnc_seconds': 0,
                'total_running_vnc_seconds': 0,
            },
        )
        user_bucket['vms'].append(vm_row)
        user_bucket['total_lifetime_seconds'] += lifetime_seconds
        user_bucket['total_stopped_seconds'] += stopped_seconds
        user_bucket['total_running_no_vnc_seconds'] += running_no_vnc_seconds
        user_bucket['total_running_vnc_seconds'] += running_vnc_seconds

    ordered = sorted(by_user.values(), key=lambda item: (item['user'].username if item['user'] else ''))
    return {
        'users': ordered,
        'generated_at': now,
        'running_warn_seconds': running_warn_seconds,
        'vnc_warn_seconds': vnc_warn_seconds,
        'format_duration': _format_duration,
    }
