import re

from flask_sqlalchemy import SQLAlchemy

from resolver import resolve_domain

db = SQLAlchemy()


class Resource(db.Model):
    __tablename__ = 'resource'

    STATUS_ERROR = 'error'
    STATUS_RESOLVED = 'resolved'
    STATUS_UNRESOLVED = 'unresolved'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True, nullable=False)
    status = db.Column(db.String, nullable=False, default=STATUS_ERROR)
    resource_type = db.Column(db.String, nullable=False)
    description = db.Column(db.String, nullable=True, unique=False)
    order = db.Column(db.String, nullable=True, unique=False)
    added_date = db.Column(db.Date(), nullable=True)
    resolve_time = db.Column(db.DateTime(timezone=True))
    ips = db.relationship('IP', cascade='all, delete')

    def __repr__(self):
        return f'<Resource {self.resource}>'

    def resolve(self):
        resolved = set()

        ip_pattern = r'\d{1,}\.\d{1,}\.\d{1,}\.\d{1,}'

        if re.match(ip_pattern, self.name):
            if self.name.endswith('/32'):
                resolved.add(self.name[:-3])
            else:
                resolved.add(self.name)

        else:
            resolved_ips = resolve_domain(self.name)
            resolved = set(resolved_ips)

        return resolved


class IP(db.Model):
    __tablename__ = 'ip'

    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String, nullable=False)
    resource_id = db.Column(db.Integer, db.ForeignKey('resource.id', ondelete='CASCADE'), nullable=False)
    resource = db.relationship('Resource')

    def __repr__(self):
        return f'<IP {self.ip}>'
