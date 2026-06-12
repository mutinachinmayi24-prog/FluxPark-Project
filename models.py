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


class ParkingSlot(db.Model):
    __tablename__ = "parking_slot"
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("property.id"), nullable=False)
    sub_room_id = db.Column(db.Integer, db.ForeignKey("sub_room.id"), nullable=True)
    slot_number = db.Column(db.String(20), nullable=False)
    floor = db.Column(db.String(20), nullable=True)
    entrance_rank = db.Column(db.Integer, nullable=False, default=0)
    ramp_rank = db.Column(db.Integer, nullable=False, default=0)
    home_role_profile_id = db.Column(db.Integer, db.ForeignKey("role_profile.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("property_id", "slot_number", name="uq_parking_slot_property_number"),
    )

    home_role_profile = db.relationship(
        "RoleProfile", foreign_keys=[home_role_profile_id], backref="parking_slots"
    )


class SlotAvailability(db.Model):
    __tablename__ = "slot_availability"
    id = db.Column(db.Integer, primary_key=True)
    parking_slot_id = db.Column(db.Integer, db.ForeignKey("parking_slot.id"), nullable=False)
    role_profile_id = db.Column(db.Integer, db.ForeignKey("role_profile.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    from_time = db.Column(db.Time, nullable=False)
    to_time = db.Column(db.Time, nullable=False)
    rent_per_hour = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="available")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    parking_slot = db.relationship("ParkingSlot", backref="availabilities")
    role_profile = db.relationship("RoleProfile", backref="slot_availabilities")


class VisitorRequest(db.Model):
    __tablename__ = "visitor_request"
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("property.id"), nullable=False)
    host_role_profile_id = db.Column(db.Integer, db.ForeignKey("role_profile.id"), nullable=False)
    visitor_name = db.Column(db.String(100), nullable=False)
    visitor_phone = db.Column(db.String(15), nullable=False)
    vehicle_type = db.Column(db.String(20), nullable=False)
    vehicle_number = db.Column(db.String(20), nullable=False)
    date = db.Column(db.Date, nullable=False)
    from_time = db.Column(db.Time, nullable=False)
    to_time = db.Column(db.Time, nullable=False)
    purpose = db.Column(db.String(200), nullable=True)
    is_unexpected = db.Column(db.Boolean, default=False, nullable=False)
    created_by_role_profile_id = db.Column(db.Integer, db.ForeignKey("role_profile.id"), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending_allocation")
    slot_availability_id = db.Column(db.Integer, db.ForeignKey("slot_availability.id"), nullable=True)
    qr_token = db.Column(db.String(32), unique=True, nullable=False, default=generate_token)
    entry_time = db.Column(db.DateTime, nullable=True)
    exit_time = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    host_role_profile = db.relationship(
        "RoleProfile", foreign_keys=[host_role_profile_id], backref="visitor_requests"
    )
    created_by_role_profile = db.relationship(
        "RoleProfile", foreign_keys=[created_by_role_profile_id]
    )
    slot_availability = db.relationship(
        "SlotAvailability", backref=db.backref("visitor_request", uselist=False)
    )


class TransportRequest(db.Model):
    __tablename__ = "transport_request"
    id = db.Column(db.Integer, primary_key=True)
    role_profile_id = db.Column(db.Integer, db.ForeignKey("role_profile.id"), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey("property.id"), nullable=False)
    sub_room_id = db.Column(db.Integer, db.ForeignKey("sub_room.id"), nullable=True)
    date = db.Column(db.Date, nullable=False)
    vehicle_type = db.Column(db.String(20), nullable=False)
    vehicle_number = db.Column(db.String(20), nullable=False)
    from_time = db.Column(db.Time, nullable=False)
    to_time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending_allocation")
    parking_slot_id = db.Column(db.Integer, db.ForeignKey("parking_slot.id"), nullable=True)
    qr_token = db.Column(db.String(32), unique=True, nullable=False, default=generate_token)
    entry_time = db.Column(db.DateTime, nullable=True)
    exit_time = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("role_profile_id", "date", name="uq_transport_request_profile_date"),
    )

    role_profile = db.relationship("RoleProfile", backref="transport_requests")
    parking_slot = db.relationship("ParkingSlot", backref="transport_requests")


class Notification(db.Model):
    __tablename__ = "notification"
    id = db.Column(db.Integer, primary_key=True)
    role_profile_id = db.Column(db.Integer, db.ForeignKey("role_profile.id"), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(300), nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    role_profile = db.relationship("RoleProfile", backref="notifications")


class Transaction(db.Model):
    __tablename__ = "transaction"
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("property.id"), nullable=False)
    payer_role_profile_id = db.Column(db.Integer, db.ForeignKey("role_profile.id"), nullable=False)
    payee_role_profile_id = db.Column(db.Integer, db.ForeignKey("role_profile.id"), nullable=False)
    visitor_request_id = db.Column(db.Integer, db.ForeignKey("visitor_request.id"), nullable=True)
    base_amount = db.Column(db.Float, nullable=False)
    commission_percent = db.Column(db.Float, nullable=False, default=0.0)
    commission_amount = db.Column(db.Float, nullable=False, default=0.0)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    description = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    payer_role_profile = db.relationship("RoleProfile", foreign_keys=[payer_role_profile_id])
    payee_role_profile = db.relationship("RoleProfile", foreign_keys=[payee_role_profile_id])
    visitor_request = db.relationship("VisitorRequest", backref="transactions")
