"""Parking slots, map, and availability routes."""

from fastapi import APIRouter
from starlette.requests import Request

from constants import RESIDENTIAL_PROPERTY_TYPES
from database import db
from helpers import (
    _parse_date,
    _parse_time,
    _require_role_profile,
    _role_profile_label,
    _strip,
    _today_transport_allocations,
    _today_visitor_allocations,
)
from i18n import _
from models import ParkingSlot, Property, RoleProfile, SlotAvailability
from parking_engine import (
    compute_slot_status,
    handle_emergency_return,
    now_ist,
    try_match_availability,
)
from templating import render
from webcompat import abort, flash, login_required, redirect, url_for

router = APIRouter()


@router.api_route("/parking-slots", methods=["GET", "POST"], name="parking_slots")
@login_required
async def parking_slots(request: Request):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    prop = Property.query.get(role_profile.property_id)
    is_office = prop.property_type not in RESIDENTIAL_PROPERTY_TYPES
    can_edit = role_profile.role in ("owner", "committee", "manager")

    if request.method == "POST":
        if not can_edit:
            abort(403)

        form = await request.form()
        slot_ids = form.getlist("slot_id[]")
        slot_numbers = form.getlist("slot_number[]")
        floors = form.getlist("floor[]")
        entrance_ranks = form.getlist("entrance_rank[]")
        ramp_ranks = form.getlist("ramp_rank[]")
        home_ids = form.getlist("home_role_profile_id[]")

        seen_numbers = set()
        errors = []
        rows = []
        for i, raw_number in enumerate(slot_numbers):
            slot_number = raw_number.strip()
            if not slot_number:
                continue
            if slot_number in seen_numbers:
                errors.append(
                    _(
                        "Duplicate slot number '%(slot_number)s' in the table.",
                        slot_number=slot_number,
                    )
                )
                continue
            seen_numbers.add(slot_number)

            try:
                entrance_rank = int(entrance_ranks[i]) if entrance_ranks[i].strip() else 0
                ramp_rank = int(ramp_ranks[i]) if ramp_ranks[i].strip() else 0
            except (ValueError, IndexError):
                errors.append(
                    _(
                        "Entrance/ramp rank for slot '%(slot_number)s' must be a number.",
                        slot_number=slot_number,
                    )
                )
                continue

            home_id = home_ids[i].strip() if i < len(home_ids) else ""
            rows.append(
                {
                    "slot_id": slot_ids[i].strip() if i < len(slot_ids) else "",
                    "slot_number": slot_number,
                    "floor": floors[i].strip() if i < len(floors) else None,
                    "entrance_rank": entrance_rank,
                    "ramp_rank": ramp_rank,
                    "home_role_profile_id": int(home_id) if home_id.isdigit() else None,
                }
            )

        if not errors:
            existing = {
                s.slot_number: s
                for s in ParkingSlot.query.filter_by(property_id=role_profile.property_id).all()
            }
            for row in rows:
                slot_id = row["slot_id"]
                if slot_id.isdigit():
                    slot = ParkingSlot.query.get(int(slot_id))
                    if slot is None or slot.property_id != role_profile.property_id:
                        continue
                    if is_office and slot.sub_room_id != role_profile.sub_room_id:
                        continue
                    clash = existing.get(row["slot_number"])
                    if clash is not None and clash.id != slot.id:
                        errors.append(
                            _(
                                "Slot number '%(slot_number)s' is already in use.",
                                slot_number=row["slot_number"],
                            )
                        )
                        continue
                    existing.pop(slot.slot_number, None)
                    slot.slot_number = row["slot_number"]
                    slot.floor = row["floor"]
                    slot.entrance_rank = row["entrance_rank"]
                    slot.ramp_rank = row["ramp_rank"]
                    slot.home_role_profile_id = row["home_role_profile_id"]
                    existing[slot.slot_number] = slot
                else:
                    if row["slot_number"] in existing:
                        errors.append(
                            _(
                                "Slot number '%(slot_number)s' is already in use.",
                                slot_number=row["slot_number"],
                            )
                        )
                        continue
                    new_slot = ParkingSlot(
                        property_id=role_profile.property_id,
                        sub_room_id=role_profile.sub_room_id if is_office else None,
                        slot_number=row["slot_number"],
                        floor=row["floor"],
                        entrance_rank=row["entrance_rank"],
                        ramp_rank=row["ramp_rank"],
                        home_role_profile_id=row["home_role_profile_id"],
                    )
                    db.session.add(new_slot)
                    existing[row["slot_number"]] = new_slot

        if errors:
            for error in errors:
                flash(error, "danger")
            db.session.rollback()
        else:
            db.session.commit()
            flash(_("Parking layout updated."), "success")
        return redirect(url_for("parking_slots"))

    slot_query = ParkingSlot.query.filter_by(property_id=role_profile.property_id)
    if is_office:
        slot_query = slot_query.filter_by(sub_room_id=role_profile.sub_room_id)
    slots = slot_query.order_by(ParkingSlot.entrance_rank, ParkingSlot.slot_number).all()
    today = now_ist().date()
    now_dt = now_ist()
    slot_rows = [(slot, compute_slot_status(slot, today, now_dt)) for slot in slots]
    today_allocations = _today_transport_allocations(role_profile.property_id, today)
    today_visitor_alloc = _today_visitor_allocations(role_profile.property_id, today)

    residents = []
    if can_edit:
        if is_office:
            residents = RoleProfile.query.filter(
                RoleProfile.property_id == role_profile.property_id,
                RoleProfile.sub_room_id == role_profile.sub_room_id,
                RoleProfile.role.in_(("employee", "manager")),
            ).all()
        else:
            residents = RoleProfile.query.filter(
                RoleProfile.property_id == role_profile.property_id,
                RoleProfile.role.in_(("owner", "tenant", "committee")),
            ).all()

    return render(
        request,
        "parking_slots.html",
        role_profile=role_profile,
        property=prop,
        slot_rows=slot_rows,
        today_allocations=today_allocations,
        today_visitor_allocations=today_visitor_alloc,
        residents=residents,
        can_edit=can_edit,
        role_profile_label=_role_profile_label,
        show_sidebar=True,
    )


@router.api_route("/parking-map", methods=["GET"], name="parking_map")
@login_required
async def parking_map(request: Request):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    prop = Property.query.get(role_profile.property_id)
    is_office = prop.property_type not in RESIDENTIAL_PROPERTY_TYPES

    slot_query = ParkingSlot.query.filter_by(property_id=role_profile.property_id)
    if is_office:
        slot_query = slot_query.filter_by(sub_room_id=role_profile.sub_room_id)
    slots = slot_query.order_by(ParkingSlot.entrance_rank, ParkingSlot.slot_number).all()
    today = now_ist().date()
    now_dt = now_ist()

    floors = {}
    for slot in slots:
        floor_key = slot.floor or "Unassigned"
        floors.setdefault(floor_key, []).append((slot, compute_slot_status(slot, today, now_dt)))

    return render(
        request,
        "parking_map.html",
        role_profile=role_profile,
        property=prop,
        floors=floors,
        show_sidebar=True,
    )


@router.api_route("/parking-availability", methods=["GET", "POST"], name="parking_availability")
@login_required
async def parking_availability(request: Request):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role not in ("owner", "tenant", "committee"):
        abort(403)

    my_slots = (
        ParkingSlot.query.filter_by(
            property_id=role_profile.property_id, home_role_profile_id=role_profile.id
        )
        .order_by(ParkingSlot.slot_number)
        .all()
    )

    form_data = {}
    if request.method == "POST":
        form = await request.form()
        form_data = form
        slot_id = _strip(form, "parking_slot_id")
        date_str = _strip(form, "date")
        from_str = _strip(form, "from_time")
        to_str = _strip(form, "to_time")
        rent_str = _strip(form, "rent_per_hour")

        errors = []
        slot = ParkingSlot.query.get(int(slot_id)) if slot_id.isdigit() else None
        if not slot or slot.home_role_profile_id != role_profile.id:
            errors.append(_("Please select a valid parking slot of yours."))
        if not date_str or not from_str or not to_str:
            errors.append(_("Please fill in date, from time and to time."))

        rent = None
        try:
            rent = float(rent_str)
            if rent <= 0:
                errors.append(_("Rent per hour must be greater than zero."))
        except (ValueError, TypeError):
            errors.append(_("Please enter a valid rent per hour."))

        if not errors:
            availability = SlotAvailability(
                parking_slot_id=slot.id,
                role_profile_id=role_profile.id,
                date=_parse_date(date_str),
                from_time=_parse_time(from_str),
                to_time=_parse_time(to_str),
                rent_per_hour=rent,
                status="available",
            )
            db.session.add(availability)
            db.session.flush()
            try_match_availability(availability)
            db.session.commit()
            if availability.status == "matched":
                flash(_("Slot listed and already matched with a waiting visitor!"), "success")
            else:
                flash(_("Your parking slot has been listed as available."), "success")
            return redirect(url_for("parking_availability"))

        for error in errors:
            flash(error, "danger")

    availabilities = (
        SlotAvailability.query.filter_by(role_profile_id=role_profile.id)
        .order_by(SlotAvailability.date.desc(), SlotAvailability.from_time.desc())
        .all()
    )

    return render(
        request,
        "parking_availability.html",
        role_profile=role_profile,
        my_slots=my_slots,
        availabilities=availabilities,
        form_data=form_data,
        show_sidebar=True,
    )


@router.api_route(
    "/parking-availability/{availability_id}/return",
    methods=["POST"],
    name="parking_availability_return",
)
@login_required
async def parking_availability_return(request: Request, availability_id: int):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    availability = SlotAvailability.query.get(availability_id)
    if availability is None:
        abort(404)
    if availability.role_profile_id != role_profile.id:
        abort(403)
    if availability.status != "matched":
        flash(_("This slot isn't currently matched with a visitor."), "warning")
        return redirect(url_for("parking_availability"))

    handle_emergency_return(availability, now_ist())
    flash(_("Marked as returned. We've notified everyone affected."), "success")
    return redirect(url_for("parking_availability"))
