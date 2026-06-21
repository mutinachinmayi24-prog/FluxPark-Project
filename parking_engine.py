"""Parking allocation engine: matching, notifications, transactions, slot status.

All matching/allocation runs event-driven (on demand) inside request handlers -
there is no background scheduler. Times are treated as naive Asia/Kolkata
wall-clock values throughout.
"""

from datetime import datetime, time, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from i18n import lazy_gettext as _l
from webcompat import url_for

from database import db
from models import (
    Notification,
    ParkingSlot,
    RoleProfile,
    SlotAvailability,
    Transaction,
    TransportRequest,
    VisitorRequest,
)

IST = ZoneInfo("Asia/Kolkata")
BUFFER_MINUTES = 15

SLOT_STATUS_LABELS = {"vacant": _l("Vacant"), "booked": _l("Booked"), "occupied": _l("Occupied")}
SLOT_STATUS_CLASSES = {"vacant": "success", "booked": "warning", "occupied": "secondary"}

REQUEST_STATUS_LABELS = {
    "pending_allocation": _l("Pending allocation"),
    "pending_approval": _l("Pending approval"),
    "allocated": _l("Allocated"),
    "no_slot": _l("No slot available"),
    "entered": _l("Entered"),
    "exited": _l("Exited"),
    "rejected": _l("Rejected"),
    "needs_reallocation": _l("Needs reallocation"),
    "cancelled": _l("Cancelled"),
}
REQUEST_STATUS_CLASSES = {
    "pending_allocation": "warning",
    "pending_approval": "info",
    "allocated": "primary",
    "no_slot": "danger",
    "entered": "success",
    "exited": "secondary",
    "rejected": "danger",
    "needs_reallocation": "danger",
    "cancelled": "secondary",
}


def now_ist():
    """Current wall-clock time in IST, as a naive datetime."""
    return datetime.now(IST).replace(tzinfo=None)


def _combine(d, t):
    return datetime.combine(d, t)


def _duration_hours(d, from_time, to_time):
    start = _combine(d, from_time)
    end = _combine(d, to_time)
    if end <= start:
        end += timedelta(days=1)
    return (end - start).total_seconds() / 3600


def _window(d, from_time, to_time):
    start = _combine(d, from_time)
    end = _combine(d, to_time)
    if end <= start:
        end += timedelta(days=1)
    return start, end


def _fits_with_buffer(avail, req):
    """True if `avail`'s window covers `req`'s window with >= 15 min buffer on each side."""
    if avail.date != req.date:
        return False
    avail_start, avail_end = _window(avail.date, avail.from_time, avail.to_time)
    req_start, req_end = _window(req.date, req.from_time, req.to_time)
    buffer = timedelta(minutes=BUFFER_MINUTES)
    return avail_start <= req_start - buffer and avail_end >= req_end + buffer


def _slack_minutes(avail, req):
    avail_start, avail_end = _window(avail.date, avail.from_time, avail.to_time)
    req_start, req_end = _window(req.date, req.from_time, req.to_time)
    return ((req_start - avail_start) + (avail_end - req_end)).total_seconds() / 60


def _rank_candidates(candidates, req):
    return sorted(
        candidates,
        key=lambda a: (_slack_minutes(a, req), a.parking_slot.entrance_rank, a.parking_slot.ramp_rank),
    )


def _pass_link(token):
    return url_for("visitor_pass", token=token)


def generate_parking_slots(property_id, count):
    """Create P-1..P-N parking slots for a newly-created residential property."""
    existing_numbers = {
        s.slot_number for s in ParkingSlot.query.filter_by(property_id=property_id).all()
    }
    rank = len(existing_numbers)
    for i in range(1, count + 1):
        slot_number = f"P-{i}"
        if slot_number in existing_numbers:
            continue
        rank += 1
        db.session.add(
            ParkingSlot(
                property_id=property_id,
                slot_number=slot_number,
                entrance_rank=rank,
                ramp_rank=rank,
            )
        )
    db.session.commit()


def generate_office_parking_slots(property_id, sub_room):
    """Create parking slots for one company (SubRoom) of a newly-created office property."""
    count = (sub_room.num_parking_spaces or 0) + (sub_room.extra_parking or 0)
    if count <= 0:
        return

    existing = ParkingSlot.query.filter_by(property_id=property_id).all()
    existing_numbers = {s.slot_number for s in existing}
    other_company_prefixes = {
        s.slot_number.split("-")[0] for s in existing if s.sub_room_id != sub_room.id
    }
    rank = len(existing)

    prefix = "".join(ch for ch in sub_room.company_name.upper() if ch.isalnum())[:3] or "CO"
    if prefix in other_company_prefixes:
        prefix = f"{prefix}{sub_room.id}"

    for i in range(1, count + 1):
        rank += 1
        slot_number = f"{prefix}-{i}"
        if slot_number in existing_numbers:
            continue
        db.session.add(
            ParkingSlot(
                property_id=property_id,
                sub_room_id=sub_room.id,
                slot_number=slot_number,
                floor=sub_room.floor_allocation or None,
                entrance_rank=rank,
                ramp_rank=rank,
            )
        )
    db.session.flush()


def link_home_slot(role_profile, parking_space_number):
    """Link (or create) the ParkingSlot matching `parking_space_number` to this resident."""
    parking_space_number = (parking_space_number or "").strip()
    if not parking_space_number:
        return

    slot = ParkingSlot.query.filter_by(
        property_id=role_profile.property_id, slot_number=parking_space_number
    ).first()
    if slot is None:
        max_rank = (
            db.session.query(db.func.max(ParkingSlot.entrance_rank))
            .filter_by(property_id=role_profile.property_id)
            .scalar()
            or 0
        )
        slot = ParkingSlot(
            property_id=role_profile.property_id,
            slot_number=parking_space_number,
            entrance_rank=max_rank + 1,
            ramp_rank=max_rank + 1,
        )
        db.session.add(slot)

    slot.home_role_profile_id = role_profile.id
    db.session.commit()


def notify(role_profile_id, title, message, link=None):
    db.session.add(
        Notification(role_profile_id=role_profile_id, title=title, message=message, link=link)
    )


def committee_commission_percent(property_id):
    committee = RoleProfile.query.filter_by(property_id=property_id, role="committee").first()
    if committee and committee.bank_detail and committee.bank_detail.commission_percent:
        return committee.bank_detail.commission_percent
    return 0.0


def create_transaction(visitor_request, availability):
    hours = _duration_hours(visitor_request.date, visitor_request.from_time, visitor_request.to_time)
    base_amount = round(availability.rent_per_hour * hours, 2)
    commission_percent = committee_commission_percent(availability.parking_slot.property_id)
    commission_amount = round(base_amount * commission_percent / 100, 2)
    total_amount = round(base_amount + commission_amount, 2)

    txn = Transaction(
        property_id=availability.parking_slot.property_id,
        payer_role_profile_id=visitor_request.host_role_profile_id,
        payee_role_profile_id=availability.role_profile_id,
        visitor_request_id=visitor_request.id,
        base_amount=base_amount,
        commission_percent=commission_percent,
        commission_amount=commission_amount,
        total_amount=total_amount,
        status="pending",
        description=f"Visitor parking - {visitor_request.visitor_name} on {visitor_request.date}",
    )
    db.session.add(txn)
    return txn


def _company_manager(property_id, sub_room_id):
    if sub_room_id is None:
        return None
    return RoleProfile.query.filter_by(
        property_id=property_id, sub_room_id=sub_room_id, role="manager"
    ).first()


def create_cross_company_transaction(
    property_id, payer_sub_room_id, payee_sub_room_id, date, from_time, to_time, description, visitor_request_id=None
):
    """Bill the payer company's manager for using the payee company's spare slot.

    No-op if either company has no manager, or the payee's manager hasn't set
    a rent_per_hour rate (i.e. spare-slot use is free until configured).
    """
    payer_manager = _company_manager(property_id, payer_sub_room_id)
    payee_manager = _company_manager(property_id, payee_sub_room_id)
    if not payer_manager or not payee_manager or payer_manager.id == payee_manager.id:
        return None

    rent_per_hour = payee_manager.bank_detail.rent_per_hour if payee_manager.bank_detail else None
    if not rent_per_hour:
        return None

    hours = _duration_hours(date, from_time, to_time)
    base_amount = round(rent_per_hour * hours, 2)

    txn = Transaction(
        property_id=property_id,
        payer_role_profile_id=payer_manager.id,
        payee_role_profile_id=payee_manager.id,
        visitor_request_id=visitor_request_id,
        base_amount=base_amount,
        total_amount=base_amount,
        status="pending",
        description=description,
    )
    db.session.add(txn)
    return txn


def _summaries(visitor_request, availability):
    slot = availability.parking_slot
    visitor_summary = (
        f"Visitor: {visitor_request.visitor_name} ({visitor_request.visitor_phone}), "
        f"{visitor_request.vehicle_type} {visitor_request.vehicle_number}, "
        f"on {visitor_request.date} from {visitor_request.from_time.strftime('%H:%M')} "
        f"to {visitor_request.to_time.strftime('%H:%M')}."
    )
    floor_part = f" (Floor {slot.floor})" if slot.floor else ""
    slot_summary = (
        f"Parking slot {slot.slot_number}{floor_part}, available "
        f"{availability.date} {availability.from_time.strftime('%H:%M')}-"
        f"{availability.to_time.strftime('%H:%M')} at ₹{availability.rent_per_hour}/hr."
    )
    return visitor_summary, slot_summary


def _allocate(visitor_request, availability):
    visitor_request.slot_availability_id = availability.id
    visitor_request.status = "allocated"
    availability.status = "matched"
    create_transaction(visitor_request, availability)

    visitor_summary, slot_summary = _summaries(visitor_request, availability)
    pass_link = _pass_link(visitor_request.qr_token)

    notify(
        visitor_request.host_role_profile_id,
        "Visitor parking allocated",
        f"{visitor_summary} Allocated {slot_summary} Visitor pass: {pass_link}",
        link=pass_link,
    )
    notify(
        availability.role_profile_id,
        "Your parking slot has been allocated to a visitor",
        f"Your slot {availability.parking_slot.slot_number} has been allocated to a visitor. "
        f"{visitor_summary} Visitor pass: {pass_link}",
        link=pass_link,
    )
    db.session.commit()


def try_match_request(visitor_request):
    """Find the best free SlotAvailability for a pending_allocation visitor request."""
    if visitor_request.status != "pending_allocation":
        return None

    candidates = (
        SlotAvailability.query.join(ParkingSlot)
        .filter(
            SlotAvailability.status == "available",
            SlotAvailability.date == visitor_request.date,
            ParkingSlot.property_id == visitor_request.property_id,
        )
        .all()
    )
    candidates = [a for a in candidates if _fits_with_buffer(a, visitor_request)]
    if not candidates:
        return None

    best = _rank_candidates(candidates, visitor_request)[0]
    _allocate(visitor_request, best)
    return best


def try_match_availability(availability):
    """Find the best pending_allocation visitor request for a newly-freed slot."""
    if availability.status != "available":
        return None

    requests = VisitorRequest.query.filter_by(
        status="pending_allocation",
        date=availability.date,
        property_id=availability.parking_slot.property_id,
    ).all()
    requests = [r for r in requests if _fits_with_buffer(availability, r)]
    if not requests:
        return None

    requests.sort(key=lambda r: _slack_minutes(availability, r))
    best = requests[0]
    _allocate(best, availability)
    return best


def allocate_transport_requests(property_id, target_date):
    """Match pending TransportRequests for `target_date` to free ParkingSlots.

    Each request is matched within its own company (sub_room) first; if none of
    that company's slots are free, it overflows to a free slot belonging to
    another company in the same property (cross-company allocation).
    """
    pending = (
        TransportRequest.query.filter_by(
            property_id=property_id, date=target_date, status="pending_allocation"
        )
        .order_by(TransportRequest.created_at, TransportRequest.id)
        .all()
    )
    if not pending:
        return

    slots = (
        ParkingSlot.query.filter_by(property_id=property_id)
        .order_by(ParkingSlot.entrance_rank, ParkingSlot.ramp_rank)
        .all()
    )
    taken = {
        tr.parking_slot_id
        for tr in TransportRequest.query.filter(
            TransportRequest.property_id == property_id,
            TransportRequest.date == target_date,
            TransportRequest.parking_slot_id.isnot(None),
        ).all()
    }
    taken |= {
        vr.parking_slot_id
        for vr in VisitorRequest.query.filter(
            VisitorRequest.property_id == property_id,
            VisitorRequest.date == target_date,
            VisitorRequest.parking_slot_id.isnot(None),
        ).all()
    }

    for req in pending:
        own = [s for s in slots if s.sub_room_id == req.sub_room_id and s.id not in taken]
        other = [s for s in slots if s.sub_room_id != req.sub_room_id and s.id not in taken]
        chosen = own[0] if own else (other[0] if other else None)

        if chosen is None:
            req.status = "no_slot"
            notify(
                req.role_profile_id,
                "No parking slot available",
                f"No parking slot was available for {target_date.strftime('%d %b %Y')}. "
                f"We'll allocate one if a slot frees up.",
                link=url_for("transport_request"),
            )
            continue

        req.parking_slot_id = chosen.id
        req.status = "allocated"
        taken.add(chosen.id)
        cross_company = chosen.sub_room_id != req.sub_room_id
        note = "" if not cross_company else " from another company's spare capacity"
        pass_link = url_for("transport_pass", token=req.qr_token)
        notify(
            req.role_profile_id,
            "Parking slot allocated",
            f"Slot {chosen.slot_number} has been allocated to you for "
            f"{target_date.strftime('%d %b %Y')}{note}. Show your pass at the gate: {pass_link}",
            link=pass_link,
        )

        if cross_company:
            employee_label = req.role_profile.data.get("employee_name") or "Employee"
            create_cross_company_transaction(
                property_id=property_id,
                payer_sub_room_id=req.sub_room_id,
                payee_sub_room_id=chosen.sub_room_id,
                date=target_date,
                from_time=req.from_time,
                to_time=req.to_time,
                description=f"Slot {chosen.slot_number} used by {employee_label} on {target_date.strftime('%d %b %Y')}",
            )

    db.session.commit()


def allocate_unexpected_visitor(visitor_request):
    """Allocate a parking slot for an approved office unexpected-visitor request.

    Tries a free slot belonging to the visited employee's company first; if
    none is free, falls back to any free slot elsewhere in the property
    (mirrors the cross-company overflow in allocate_transport_requests).
    """
    if visitor_request.status != "pending_allocation":
        return None

    host = visitor_request.host_role_profile
    now_dt = now_ist()

    slots = (
        ParkingSlot.query.filter_by(property_id=visitor_request.property_id)
        .order_by(ParkingSlot.entrance_rank, ParkingSlot.ramp_rank)
        .all()
    )
    own = [s for s in slots if s.sub_room_id == host.sub_room_id]
    other = [s for s in slots if s.sub_room_id != host.sub_room_id]

    chosen = None
    for slot in own + other:
        if compute_slot_status(slot, visitor_request.date, now_dt) == "vacant":
            chosen = slot
            break

    pass_link = _pass_link(visitor_request.qr_token)

    if chosen is None:
        visitor_request.status = "no_slot"
        notify(
            visitor_request.host_role_profile_id,
            "Visitor approved, no parking slot available",
            f"Visitor {visitor_request.visitor_name} ({visitor_request.visitor_phone}) was approved "
            f"but no parking slot is free right now. We'll allocate one if a slot frees up.",
            link=pass_link,
        )
        if visitor_request.created_by_role_profile_id:
            notify(
                visitor_request.created_by_role_profile_id,
                "Visitor approved, no parking slot available",
                f"Visitor {visitor_request.visitor_name} ({visitor_request.visitor_phone}), "
                f"{visitor_request.vehicle_type} {visitor_request.vehicle_number} was approved "
                f"but no parking slot is free right now.",
                link=pass_link,
            )
        db.session.commit()
        return None

    visitor_request.parking_slot_id = chosen.id
    visitor_request.status = "allocated"
    cross_company = chosen.sub_room_id != host.sub_room_id
    note = "" if not cross_company else " from another company's spare capacity"
    floor_part = f" (Floor {chosen.floor})" if chosen.floor else ""

    notify(
        visitor_request.host_role_profile_id,
        "Visitor parking allocated",
        f"Visitor {visitor_request.visitor_name} ({visitor_request.visitor_phone}), "
        f"{visitor_request.vehicle_type} {visitor_request.vehicle_number} has been allocated "
        f"slot {chosen.slot_number}{floor_part}{note}. Visitor pass: {pass_link}",
        link=pass_link,
    )
    if visitor_request.created_by_role_profile_id:
        notify(
            visitor_request.created_by_role_profile_id,
            "Visitor parking allocated",
            f"Visitor {visitor_request.visitor_name} ({visitor_request.visitor_phone}) has been "
            f"allocated slot {chosen.slot_number}{floor_part}{note}. Pass: {pass_link}",
            link=pass_link,
        )

    if cross_company:
        host_label = host.data.get("employee_name") or "Employee"
        create_cross_company_transaction(
            property_id=visitor_request.property_id,
            payer_sub_room_id=host.sub_room_id,
            payee_sub_room_id=chosen.sub_room_id,
            date=visitor_request.date,
            from_time=visitor_request.from_time,
            to_time=visitor_request.to_time,
            description=(
                f"Slot {chosen.slot_number} used by visitor {visitor_request.visitor_name} "
                f"visiting {host_label} on {visitor_request.date.strftime('%d %b %Y')}"
            ),
            visitor_request_id=visitor_request.id,
        )

    db.session.commit()
    return chosen


def run_pending_transport_allocations(property_id, now_dt):
    """Allocate any TransportRequests whose 9 PM submission cutoff has passed."""
    today = now_dt.date()
    cutoff_date = today + timedelta(days=1) if now_dt.time() >= time(21, 0) else today

    pending_dates = (
        db.session.query(TransportRequest.date)
        .filter(
            TransportRequest.property_id == property_id,
            TransportRequest.status == "pending_allocation",
            TransportRequest.date <= cutoff_date,
        )
        .distinct()
        .all()
    )
    for (target_date,) in pending_dates:
        allocate_transport_requests(property_id, target_date)


def compute_slot_status(slot, today, now_dt):
    """Return 'vacant' | 'booked' | 'occupied' for a parking slot right now."""
    availabilities = SlotAvailability.query.filter(
        SlotAvailability.parking_slot_id == slot.id,
        SlotAvailability.date == today,
        SlotAvailability.status.in_(("available", "matched")),
    ).all()

    for avail in availabilities:
        start, end = _window(avail.date, avail.from_time, avail.to_time)
        if start <= now_dt <= end:
            if avail.status == "available":
                return "vacant"
            visitor_request = avail.visitor_request
            if visitor_request and visitor_request.status == "entered":
                return "occupied"
            return "booked"

    transport_request = TransportRequest.query.filter(
        TransportRequest.parking_slot_id == slot.id,
        TransportRequest.date == today,
        TransportRequest.status.in_(("allocated", "entered")),
    ).first()
    if transport_request:
        if transport_request.status == "entered":
            return "occupied"
        start, end = _window(transport_request.date, transport_request.from_time, transport_request.to_time)
        if start <= now_dt <= end:
            return "occupied"
        if now_dt < start:
            return "booked"

    office_visitor = VisitorRequest.query.filter(
        VisitorRequest.parking_slot_id == slot.id,
        VisitorRequest.date == today,
        VisitorRequest.status.in_(("allocated", "entered")),
    ).first()
    if office_visitor:
        if office_visitor.status == "entered":
            return "occupied"
        start, end = _window(office_visitor.date, office_visitor.from_time, office_visitor.to_time)
        if start <= now_dt <= end:
            return "occupied"
        if now_dt < start:
            return "booked"

    return "occupied" if slot.home_role_profile_id else "vacant"


def handle_emergency_return(availability, return_dt):
    """Resident returns early: free their slot and re-route the visitor if possible.

    Returns the new SlotAvailability on success, or None if no alternate slot was
    found (or there was no visitor to reallocate).
    """
    visitor_request = availability.visitor_request
    old_slot = availability.parking_slot

    availability.status = "completed"
    availability.to_time = return_dt.time()

    if visitor_request is None or visitor_request.status not in ("allocated", "entered"):
        db.session.commit()
        return None

    remaining = SimpleNamespace(
        date=visitor_request.date,
        from_time=return_dt.time(),
        to_time=visitor_request.to_time,
    )

    candidates = (
        SlotAvailability.query.join(ParkingSlot)
        .filter(
            SlotAvailability.status == "available",
            SlotAvailability.date == visitor_request.date,
            ParkingSlot.property_id == visitor_request.property_id,
        )
        .all()
    )
    candidates = [a for a in candidates if _fits_with_buffer(a, remaining)]

    if not candidates:
        visitor_request.status = "needs_reallocation"
        notify(
            visitor_request.host_role_profile_id,
            "Visitor's parking slot needs reallocation",
            f"The owner of slot {old_slot.slot_number} has returned early and no alternate "
            f"slot is currently free for your visitor {visitor_request.visitor_name}. "
            f"Security has been notified.",
        )
        for sec in RoleProfile.query.filter_by(
            property_id=visitor_request.property_id, role="security"
        ).all():
            notify(
                sec.id,
                "Visitor needs slot reallocation",
                f"Visitor {visitor_request.visitor_name} ({visitor_request.visitor_phone}) "
                f"needs a new parking slot - the resident in slot {old_slot.slot_number} "
                f"has returned early.",
            )
        db.session.commit()
        return None

    best = _rank_candidates(candidates, remaining)[0]
    new_slot = best.parking_slot

    for txn in visitor_request.transactions:
        if txn.status == "pending":
            txn.status = "cancelled"

    visitor_request.slot_availability_id = best.id
    best.status = "matched"
    create_transaction(visitor_request, best)

    pass_link = _pass_link(visitor_request.qr_token)
    floor_part = f" (Floor {new_slot.floor})" if new_slot.floor else ""

    notify(
        best.role_profile_id,
        "Your parking slot has been allocated to a visitor",
        f"A visitor has been reallocated to your slot {new_slot.slot_number} due to another "
        f"resident's emergency return. Visitor: {visitor_request.visitor_name} "
        f"({visitor_request.visitor_phone}), {visitor_request.vehicle_type} "
        f"{visitor_request.vehicle_number}. Visitor pass: {pass_link}",
        link=pass_link,
    )
    notify(
        visitor_request.host_role_profile_id,
        "Visitor's parking slot has changed",
        f"Sorry for the inconvenience - the original slot owner returned early. Your visitor "
        f"{visitor_request.visitor_name} has been reallocated to slot {new_slot.slot_number}"
        f"{floor_part}. Updated visitor pass: {pass_link}",
        link=pass_link,
    )
    db.session.commit()
    return best
