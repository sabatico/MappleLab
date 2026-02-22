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
    password_hash = db.Column(db.String(128), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_saved_at = db.Column(db.DateTime, nullable=True)
    last_started_at = db.Column(db.DateTime, nullable=True)
    status_detail = db.Column(db.String(256), nullable=True)  # error messages, progress info
