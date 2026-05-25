from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
import uuid

db = SQLAlchemy()

def gen_uuid():
    return str(uuid.uuid4())

class OLT(db.Model):
    __tablename__ = 'olts'
    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    name = db.Column(db.String(100), nullable=False)
    ip = db.Column(db.String(45), unique=True, nullable=False)
    username = db.Column(db.String(64), nullable=False)
    password = db.Column(db.String(128), nullable=False)
    type = db.Column(db.String(32), default='Huawei')
    line_profile_id = db.Column(db.String(16), default='10')
    srv_profile_id = db.Column(db.String(16), default='10')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    onts = db.relationship('ONT', backref='olt', lazy='dynamic', cascade='all, delete-orphan')

class QuickCommand(db.Model):
    __tablename__ = 'quick_commands'
    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    label = db.Column(db.String(100), nullable=False)
    commands = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class ONT(db.Model):
    __tablename__ = 'onts'
    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    olt_id = db.Column(db.String(36), db.ForeignKey('olts.id'), nullable=False)
    name = db.Column(db.String(128), default='')
    address = db.Column(db.String(256), default='')
    sn = db.Column(db.String(32), nullable=False)
    slot = db.Column(db.String(8), default='')
    pon = db.Column(db.String(8), default='')
    ont_id = db.Column(db.Integer, nullable=True)
    vlan = db.Column(db.String(16), default='')
    vlan_ids = db.Column(db.String(256), default='')
    rx_power = db.Column(db.String(32), nullable=True)
    status = db.Column(db.String(32), default='unregistered')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (db.UniqueConstraint('olt_id', 'sn', name='uq_olt_sn'),)

class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    olt_id = db.Column(db.String(36), db.ForeignKey('olts.id'), nullable=True)
    olt_name = db.Column(db.String(100), default='')
    action = db.Column(db.String(32), nullable=False)
    description = db.Column(db.String(512), default='')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
