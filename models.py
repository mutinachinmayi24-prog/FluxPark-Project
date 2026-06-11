import secrets
from datetime import datetime

from extensions import db


def generate_token():
    return secrets.token_urlsafe(12)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    phone = db.Column(db.String(15), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    role_profiles = db.relationship("RoleProfile", backref="user", lazy=True)

    @property
    def contact(self):
        return self.email or self.phone


class OTPRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contact = db.Column(db.String(120), nullable=False, index=True)
    code = db.Column(db.String(6), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    verified = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def is_expired(self):
        return datetime.utcnow() > self.expires_at


class Property(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.String(300), nullable=False)
    property_type = db.Column(db.String(20), nullable=False)
    num_flats = db.Column(db.Integer, nullable=True)
    extra_parking = db.Column(db.Integer, nullable=True, default=0)
    invite_token = db.Column(db.String(32), unique=True, nullable=False, default=generate_token)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sub_rooms = db.relationship(
        "SubRoom", backref="property", lazy=True, cascade="all, delete-orphan"
    )
    role_profiles = db.relationship("RoleProfile", backref="property", lazy=True)


class SubRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("property.id"), nullable=False)
    company_name = db.Column(db.String(150), nullable=False)
    num_employees = db.Column(db.Integer, nullable=True)
    num_parking_spaces = db.Column(db.Integer, nullable=True)
    floor_allocation = db.Column(db.String(200), nullable=True)
    extra_parking = db.Column(db.Integer, nullable=True, default=0)
    invite_token = db.Column(db.String(32), unique=True, nullable=False, default=generate_token)

    role_profiles = db.relationship("RoleProfile", backref="sub_room", lazy=True)


class RoleProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey("property.id"), nullable=False)
    sub_room_id = db.Column(db.Integer, db.ForeignKey("sub_room.id"), nullable=True)
    role = db.Column(db.String(20), nullable=False)
    data = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    vehicles = db.relationship(
        "Vehicle", backref="role_profile", lazy=True, cascade="all, delete-orphan"
    )
    bank_detail = db.relationship(
        "BankDetail",
        backref="role_profile",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Vehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role_profile_id = db.Column(db.Integer, db.ForeignKey("role_profile.id"), nullable=False)
    s_no = db.Column(db.Integer, nullable=False)
    vehicle_type = db.Column(db.String(20), nullable=False)
    vehicle_number = db.Column(db.String(20), nullable=False)


class BankDetail(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role_profile_id = db.Column(
        db.Integer, db.ForeignKey("role_profile.id"), unique=True, nullable=False
    )
    bank_name = db.Column(db.String(100))
    branch = db.Column(db.String(100))
    ifsc_code = db.Column(db.String(20))
    account_number = db.Column(db.String(30))
    expiry_date = db.Column(db.String(10))
    commission_percent = db.Column(db.Float, nullable=True)
    rent_per_hour = db.Column(db.Float, nullable=True)
