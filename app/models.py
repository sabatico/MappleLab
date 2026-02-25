from datetime import datetime
from app.extensions import db, login_manager
from flask_login import UserMixin


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=True)
    password_hash = db.Column(db.String(128), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    max_active_vms = db.Column(db.Integer, default=1, nullable=False)
    max_saved_vms = db.Column(db.Integer, default=2, nullable=False)
    disk_quota_gb = db.Column(db.Integer, default=100, nullable=False)
    must_set_password = db.Column(db.Boolean, default=False, nullable=False)
    invite_token = db.Column(db.String(128), nullable=True)
    invited_at = db.Column(db.DateTime, nullable=True)
    last_login_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    vms = db.relationship('VM', backref='owner', lazy='select')


class Node(db.Model):
    __tablename__ = 'nodes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)   # e.g. "mac-mini-01"
    host = db.Column(db.String(128), nullable=False)               # IP or hostname
    agent_port = db.Column(db.Integer, default=7000)
    ssh_user = db.Column(db.String(64), nullable=False)
    ssh_key_path = db.Column(db.String(256), nullable=False)
    max_vms = db.Column(db.Integer, default=2)
    active = db.Column(db.Boolean, default=True)
    vms = db.relationship('VM', backref='node', lazy='select')

    @property
    def agent_url(self):
        return f'http://{self.host}:{self.agent_port}'


class VM(db.Model):
    __tablename__ = 'vms'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    node_id = db.Column(db.Integer, db.ForeignKey('nodes.id'), nullable=True)  # null = archived
    status = db.Column(db.String(32), default='creating')
    # status values:
    # 'creating'  - being cloned from base image on a node
    # 'running'   - active on node_id
    # 'stopped'   - present on node_id but powered off
    # 'pushing'   - shutdown done, pushing to registry
    # 'archived'  - in registry, not on any node
    # 'pulling'   - being pulled from registry to a node
    # 'failed'    - last operation failed
    base_image = db.Column(db.String(256), nullable=False)
    registry_tag = db.Column(db.String(256), nullable=True)   # full registry path
    cpu = db.Column(db.Integer, nullable=True)
    memory_mb = db.Column(db.Integer, nullable=True)
    disk_size_gb = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_saved_at = db.Column(db.DateTime, nullable=True)
    last_started_at = db.Column(db.DateTime, nullable=True)
    status_detail = db.Column(db.String(256), nullable=True)  # error messages, progress info
    cleanup_status = db.Column(db.String(32), nullable=True)  # pending|done|warning|failed
    cleanup_last_error = db.Column(db.String(256), nullable=True)
    cleanup_last_run_at = db.Column(db.DateTime, nullable=True)
    cleanup_target_digest = db.Column(db.String(128), nullable=True)
    status_events = db.relationship('VMStatusEvent', backref='vm', lazy='select')
    vnc_sessions = db.relationship('VMVncSession', backref='vm', lazy='select')


class VMStatusEvent(db.Model):
    __tablename__ = 'vm_status_events'

    id = db.Column(db.Integer, primary_key=True)
    vm_id = db.Column(db.Integer, db.ForeignKey('vms.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    node_id = db.Column(db.Integer, db.ForeignKey('nodes.id'), nullable=True)
    from_status = db.Column(db.String(32), nullable=True)
    to_status = db.Column(db.String(32), nullable=False)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    source = db.Column(db.String(32), nullable=False)
    context = db.Column(db.String(128), nullable=True)

    __table_args__ = (
        db.Index('ix_vm_status_events_vm_id_changed_at', 'vm_id', 'changed_at'),
        db.Index('ix_vm_status_events_user_id_changed_at', 'user_id', 'changed_at'),
        db.Index('ix_vm_status_events_to_status_changed_at', 'to_status', 'changed_at'),
    )


class VMVncSession(db.Model):
    __tablename__ = 'vm_vnc_sessions'

    id = db.Column(db.Integer, primary_key=True)
    vm_id = db.Column(db.Integer, db.ForeignKey('vms.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    node_id = db.Column(db.Integer, db.ForeignKey('nodes.id'), nullable=True)
    connected_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    disconnected_at = db.Column(db.DateTime, nullable=True)
    disconnect_reason = db.Column(db.String(64), nullable=True)
    session_token = db.Column(db.String(64), unique=True, nullable=False)

    __table_args__ = (
        db.Index('ix_vm_vnc_sessions_vm_id_connected_at', 'vm_id', 'connected_at'),
        db.Index('ix_vm_vnc_sessions_user_id_connected_at', 'user_id', 'connected_at'),
        db.Index('ix_vm_vnc_sessions_session_token', 'session_token'),
    )


class AppSettings(db.Model):
    __tablename__ = 'app_settings'
    id = db.Column(db.Integer, primary_key=True)
    smtp_host = db.Column(db.String(256), nullable=True)
    smtp_port = db.Column(db.Integer, default=587, nullable=False)
    smtp_user = db.Column(db.String(256), nullable=True)
    smtp_password = db.Column(db.String(256), nullable=True)
    smtp_from = db.Column(db.String(256), nullable=True)
    smtp_use_tls = db.Column(db.Boolean, default=True, nullable=False)
    smtp_use_ssl = db.Column(db.Boolean, default=False, nullable=False)


class GoldImage(db.Model):
    __tablename__ = 'gold_images'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    registry_tag = db.Column(db.String(256), nullable=False)
    base_image = db.Column(db.String(256), nullable=True)
    disk_size_gb = db.Column(db.Float, nullable=True)
    description = db.Column(db.String(512), nullable=True)
    source_vm_name = db.Column(db.String(128), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    nodes = db.relationship('GoldImageNode', backref='gold_image', lazy='select',
                            cascade='all, delete-orphan')


class GoldImageNode(db.Model):
    __tablename__ = 'gold_image_nodes'
    id = db.Column(db.Integer, primary_key=True)
    gold_image_id = db.Column(db.Integer, db.ForeignKey('gold_images.id'), nullable=False)
    node_id = db.Column(db.Integer, db.ForeignKey('nodes.id'), nullable=False)
    # status: pending | pulling | ready | failed
    status = db.Column(db.String(32), default='pending', nullable=False)
    status_detail = db.Column(db.String(256), nullable=True)
    op_key = db.Column(db.String(256), nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    node = db.relationship('Node', backref='gold_image_nodes')

    __table_args__ = (
        db.UniqueConstraint('gold_image_id', 'node_id', name='uq_gold_image_node'),
    )
