from datetime import datetime
from app.extensions import db
from app.models import VM, VMStatusEvent, VMVncSession


def record_vm_status_transition(vm, from_status, to_status, source, context, changed_at=None):
    """
    Persist immutable VM transition telemetry.
    De-duplicates adjacent duplicate target statuses.
    """
    changed_at = changed_at or datetime.utcnow()
    latest = (
        VMStatusEvent.query
        .filter_by(vm_id=vm.id)
        .order_by(VMStatusEvent.changed_at.desc(), VMStatusEvent.id.desc())
        .first()
    )
    if latest and latest.to_status == to_status:
        return None

    event = VMStatusEvent(
        vm_id=vm.id,
        user_id=vm.user_id,
        node_id=vm.node_id,
        from_status=from_status,
        to_status=to_status,
        changed_at=changed_at,
        source=source,
        context=context,
    )
    db.session.add(event)
    return event


def ensure_vm_status_baseline(vm, source='system', context='baseline'):
    """
    Ensure at least one status event exists for this VM.
    """
    has_event = VMStatusEvent.query.filter_by(vm_id=vm.id).first()
    if has_event:
        return None
    baseline_time = vm.created_at or datetime.utcnow()
    return record_vm_status_transition(
        vm=vm,
        from_status=None,
        to_status=vm.status or 'creating',
        source=source,
        context=context,
        changed_at=baseline_time,
    )


def start_vnc_session(vm, session_token, connected_at=None):
    connected_at = connected_at or datetime.utcnow()
    session = VMVncSession(
        vm_id=vm.id,
        user_id=vm.user_id,
        node_id=vm.node_id,
        connected_at=connected_at,
        session_token=session_token,
    )
    db.session.add(session)
    return session


def close_vnc_session(session_token, disconnected_at=None, disconnect_reason=None):
    """
    Idempotently close an open VNC session by token.
    """
    disconnected_at = disconnected_at or datetime.utcnow()
    session = VMVncSession.query.filter_by(session_token=session_token).first()
    if not session or session.disconnected_at is not None:
        return session
    session.disconnected_at = disconnected_at
    if disconnect_reason:
        session.disconnect_reason = disconnect_reason[:64]
    return session


def backfill_vm_status_baselines():
    """
    Add baseline status events for any existing VMs without history.
    """
    created = 0
    for vm in VM.query.all():
        if ensure_vm_status_baseline(vm):
            created += 1
    if created:
        db.session.commit()
    return created
