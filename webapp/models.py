import re
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

from resolver import resolve_domain, DNSResolveError, DNSConnectionError

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

    def get_resolved_ips(self) -> set:
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

    def update_ips(self):
        if self.ips:
            resource_ips_db = IP.query.filter(IP.resource_id == self.id).all()
            resource_ips = {ip.ip for ip in resource_ips_db}
        else:
            resource_ips = set()

        self.resolve_time = datetime.now()

        try:
            resolved_ips = self.get_resolved_ips()

        except DNSConnectionError:
            self.status = self.STATUS_ERROR
            db.session.commit()
            raise

        except DNSResolveError:
            self.status = self.STATUS_UNRESOLVED
            IP.query.filter(IP.resource_id == self.id).delete()
            db.session.commit()
            raise

        else:
            self.status = self.STATUS_RESOLVED

        if resolved_ips:
            ips_to_add = resolved_ips - set(resource_ips)
            ips_to_delete = set(resource_ips) - resolved_ips

            for ip_to_delete in ips_to_delete:
                IP.query.filter(IP.ip == ip_to_delete, IP.resource_id == self.id).delete()

            for ip_to_add in ips_to_add:
                ip = IP()
                ip.ip = ip_to_add
                ip.resource_id = self.id
                db.session.add(ip)

        db.session.commit()


class IP(db.Model):
    __tablename__ = 'ip'

    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String, nullable=False)
    resource_id = db.Column(db.Integer, db.ForeignKey('resource.id', ondelete='CASCADE'), nullable=False)
    resource = db.relationship('Resource')

    def __repr__(self):
        return f'<IP {self.ip}>'
