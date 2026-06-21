"""Shared utilities used across multiple routers: regex constants, field lists,
form-parsing helpers, route-level role/profile guards, and label formatters.
"""

import re
from datetime import datetime, time

from constants import (
    RESIDENTIAL_PROPERTY_TYPES,
    ROLE_LABELS,
)
from database import db
from i18n import _
from models import (
    Property,
    RoleProfile,
    TransportRequest,
    Vehicle,
    VisitorRequest,
)
from webcompat import abort, redirect, session, url_for

# ---------------------------------------------------------------------------
# Regex / field constants
# ---------------------------------------------------------------------------

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_REGEX = re.compile(r"^[6-9]\d{9}$")

REQUIRED_FIELDS = {
    "owner": ["name", "phone", "flat_no", "num_parking_slots", "parking_space_number"],
    "tenant": [
        "owner_name",
        "owner_phone",
        "tenant_name",
        "tenant_phone",
        "flat_no",
        "num_parking_slots",
        "parking_space_number",
    ],
    "committee": ["head_name", "head_phone", "head_flat_no", "num_parking_slots", "parking_space_number"],
    "security": ["name", "phone", "shift_from", "shift_to"],
    "employee": ["employee_name", "employee_id", "employee_address", "shift_from", "shift_to", "transport"],
    "manager": ["employee_name", "employee_id", "employee_address", "shift_from", "shift_to", "transport"],
}

REQUIRED_BANK_FIELDS = ["bank_name", "branch", "ifsc_code", "account_number", "expiry_date"]

ROLE_TEMPLATES = {
    "owner": "role_form_owner.html",
    "tenant": "role_form_tenant.html",
    "committee": "role_form_committee.html",
    "security": "role_form_security.html",
    "employee": "role_form_employee.html",
    "manager": "role_form_manager.html",
}

TRANSPORT_REQUEST_CUTOFF = time(21, 0)


# ---------------------------------------------------------------------------
# Form helpers
# ---------------------------------------------------------------------------


def _strip(form, field):
    return form.get(field, "").strip()


def _parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_time(value):
    return datetime.strptime(value, "%H:%M").time()


def _today_transport_allocations(property_id, today):
    rows = TransportRequest.query.filter(
        TransportRequest.property_id == property_id,
        TransportRequest.date == today,
        TransportRequest.status.in_(("allocated", "entered")),
        TransportRequest.parking_slot_id.isnot(None),
    ).all()
    return {tr.parking_slot_id: tr for tr in rows}


def _today_visitor_allocations(property_id, today):
    rows = VisitorRequest.query.filter(
        VisitorRequest.property_id == property_id,
        VisitorRequest.date == today,
        VisitorRequest.status.in_(("allocated", "entered")),
        VisitorRequest.parking_slot_id.isnot(None),
    ).all()
    return {vr.parking_slot_id: vr for vr in rows}


# ---------------------------------------------------------------------------
# Role-profile guards
# ---------------------------------------------------------------------------


def _require_role_profile():
    role_profile = RoleProfile.query.get(session.get("role_profile_id"))
    if role_profile is None:
        return None, redirect(url_for("property_setup"))
    return role_profile, None


def _role_profile_label(role_profile):
    d = role_profile.data
    name = (
        d.get("name")
        or d.get("tenant_name")
        or d.get("head_name")
        or d.get("employee_name")
        or "Unknown"
    )
    role_label = str(ROLE_LABELS.get(role_profile.role, role_profile.role.title()))
    flat = d.get("flat_no") or d.get("head_flat_no")
    if flat:
        return f"{flat} - {name} ({role_label})"
    return f"{name} ({role_label})"


def _approvable_host_ids(role_profile):
    if role_profile.role == "manager" and role_profile.sub_room_id:
        return [
            rp.id
            for rp in RoleProfile.query.filter(
                RoleProfile.property_id == role_profile.property_id,
                RoleProfile.sub_room_id == role_profile.sub_room_id,
                RoleProfile.role.in_(("employee", "manager")),
            ).all()
        ]
    return [role_profile.id]


def _visitor_log_query(role_profile, prop):
    query = VisitorRequest.query.filter_by(property_id=role_profile.property_id)
    is_office = prop.property_type not in RESIDENTIAL_PROPERTY_TYPES
    if is_office and role_profile.sub_room_id:
        host_ids = [
            rp.id
            for rp in RoleProfile.query.filter_by(
                property_id=role_profile.property_id, sub_room_id=role_profile.sub_room_id
            ).all()
        ]
        query = query.filter(VisitorRequest.host_role_profile_id.in_(host_ids))
    return query


# ---------------------------------------------------------------------------
# Onboarding validation helpers
# ---------------------------------------------------------------------------


def find_duplicate_vehicle_numbers(property_id, vehicle_numbers):
    vehicle_numbers = {v for v in vehicle_numbers if v}
    if not vehicle_numbers:
        return []

    found = set()
    existing = (
        db.session.query(Vehicle.vehicle_number)
        .join(RoleProfile, Vehicle.role_profile_id == RoleProfile.id)
        .filter(RoleProfile.property_id == property_id, Vehicle.vehicle_number.in_(vehicle_numbers))
        .all()
    )
    found.update(row[0] for row in existing)

    for role_profile in RoleProfile.query.filter_by(property_id=property_id).all():
        vnum = role_profile.data.get("vehicle_number")
        if vnum in vehicle_numbers:
            found.add(vnum)

    return list(found)


def is_duplicate_employee_id(property_id, sub_room_id, employee_id):
    if not employee_id:
        return False
    query = RoleProfile.query.filter(
        RoleProfile.property_id == property_id, RoleProfile.role.in_(["employee", "manager"])
    )
    if sub_room_id:
        query = query.filter(RoleProfile.sub_room_id == sub_room_id)
    return any(role_profile.data.get("employee_id") == employee_id for role_profile in query.all())
