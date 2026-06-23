"""Dashboard, profile, and multi-room management routes."""

from datetime import datetime, timedelta

from fastapi import APIRouter
from starlette.requests import Request

from constants import VEHICLE_TYPES
from database import db
from helpers import (
    TRANSPORT_REQUEST_CUTOFF,
    _role_profile_label,
    _strip,
    _today_transport_allocations,
    _today_visitor_allocations,
)
from i18n import _
from models import (
    Notification,
    ParkingSlot,
    Property,
    RoleProfile,
    SlotAvailability,
    SubRoom,
    Transaction,
    TransportRequest,
    VisitorRequest,
)
from parking_engine import (
    compute_slot_status,
    now_ist,
    run_pending_transport_allocations,
)
from routers.auth import resolve_invite_token
from templating import render
from webcompat import abort, flash, login_required, redirect, session, url_for

router = APIRouter()


@router.api_route("/dashboard", methods=["GET"], name="dashboard")
@login_required
async def dashboard(request: Request):
    role_profile = RoleProfile.query.get(session.get("role_profile_id"))
    if role_profile is None:
        return redirect(url_for("property_setup"))

    prop = Property.query.get(role_profile.property_id)
    sub_room = SubRoom.query.get(role_profile.sub_room_id) if role_profile.sub_room_id else None

    today = now_ist().date()
    now_dt = now_ist()

    unread_count = Notification.query.filter_by(
        role_profile_id=role_profile.id, is_read=False
    ).count()
    recent_notifications = (
        Notification.query.filter_by(role_profile_id=role_profile.id)
        .order_by(Notification.created_at.desc())
        .limit(5)
        .all()
    )

    today_requests = []
    my_slot_rows = []
    today_availabilities = []
    pending_approvals = 0
    commission_today = None
    today_visitors = []
    company_slot_rows = []
    company_vacant_count = 0
    team_members = []
    today_allocations = {}
    today_visitor_allocations = {}
    tomorrow_transport_request = None
    transport_cutoff_passed = False

    if role_profile.role in ("owner", "tenant", "committee"):
        today_requests = (
            VisitorRequest.query.filter_by(host_role_profile_id=role_profile.id, date=today)
            .order_by(VisitorRequest.from_time)
            .all()
        )
        pending_approvals = VisitorRequest.query.filter_by(
            host_role_profile_id=role_profile.id, status="pending_approval"
        ).count()
        my_slots = (
            ParkingSlot.query.filter_by(
                property_id=role_profile.property_id, home_role_profile_id=role_profile.id
            )
            .order_by(ParkingSlot.slot_number)
            .all()
        )
        my_slot_rows = [(slot, compute_slot_status(slot, today, now_dt)) for slot in my_slots]
        today_availabilities = (
            SlotAvailability.query.filter_by(role_profile_id=role_profile.id, date=today)
            .order_by(SlotAvailability.from_time)
            .all()
        )
        if role_profile.role == "committee":
            day_start = datetime.combine(today, datetime.min.time())
            day_end = datetime.combine(today, datetime.max.time())
            commission_today = (
                db.session.query(db.func.sum(Transaction.commission_amount))
                .filter(
                    Transaction.property_id == role_profile.property_id,
                    Transaction.status != "cancelled",
                    Transaction.created_at >= day_start,
                    Transaction.created_at <= day_end,
                )
                .scalar()
                or 0
            )
    elif role_profile.role == "security":
        today_visitors = (
            VisitorRequest.query.filter_by(property_id=role_profile.property_id, date=today)
            .filter(VisitorRequest.status.in_(("allocated", "entered", "exited")))
            .order_by(VisitorRequest.from_time)
            .all()
        )
    elif role_profile.role in ("employee", "manager"):
        run_pending_transport_allocations(role_profile.property_id, now_dt)
        company_slots = (
            ParkingSlot.query.filter_by(
                property_id=role_profile.property_id, sub_room_id=role_profile.sub_room_id
            )
            .order_by(ParkingSlot.entrance_rank, ParkingSlot.slot_number)
            .all()
        )
        company_slot_rows = [
            (slot, compute_slot_status(slot, today, now_dt)) for slot in company_slots
        ]
        company_vacant_count = sum(1 for _, status in company_slot_rows if status == "vacant")
        today_allocations = _today_transport_allocations(role_profile.property_id, today)
        today_visitor_allocations = _today_visitor_allocations(role_profile.property_id, today)
        tomorrow = today + timedelta(days=1)
        transport_cutoff_passed = now_dt.time() >= TRANSPORT_REQUEST_CUTOFF
        tomorrow_transport_request = TransportRequest.query.filter_by(
            role_profile_id=role_profile.id, date=tomorrow
        ).first()
        if role_profile.role == "manager":
            team_members = (
                RoleProfile.query.filter_by(
                    property_id=role_profile.property_id,
                    sub_room_id=role_profile.sub_room_id,
                    role="employee",
                )
                .order_by(RoleProfile.id)
                .all()
            )

    return render(
        request,
        "dashboard.html",
        role_profile=role_profile,
        property=prop,
        sub_room=sub_room,
        unread_count=unread_count,
        recent_notifications=recent_notifications,
        today_requests=today_requests,
        pending_approvals=pending_approvals,
        my_slot_rows=my_slot_rows,
        today_availabilities=today_availabilities,
        commission_today=commission_today,
        today_visitors=today_visitors,
        company_slot_rows=company_slot_rows,
        company_vacant_count=company_vacant_count,
        team_members=team_members,
        today_allocations=today_allocations,
        today_visitor_allocations=today_visitor_allocations,
        tomorrow_transport_request=tomorrow_transport_request,
        transport_cutoff_passed=transport_cutoff_passed,
        role_profile_label=_role_profile_label,
        show_sidebar=True,
    )


@router.api_route("/my-profile", methods=["GET", "POST"], name="my_profile")
@login_required
async def my_profile(request: Request):
    role_profile = RoleProfile.query.get(session.get("role_profile_id"))
    if role_profile is None:
        return redirect(url_for("property_setup"))

    prop = Property.query.get(role_profile.property_id)
    sub_room = SubRoom.query.get(role_profile.sub_room_id) if role_profile.sub_room_id else None

    if request.method == "POST":
        form = await request.form()
        data = dict(role_profile.data)

        if role_profile.role in ("employee", "manager", "security"):
            data["shift_from"] = _strip(form, "shift_from")
            data["shift_to"] = _strip(form, "shift_to")

        if role_profile.role in ("employee", "manager") and data.get("transport") == "self":
            data["vehicle_type"] = _strip(form, "vehicle_type")
            data["vehicle_number"] = _strip(form, "vehicle_number").upper()

        role_profile.data = data

        if role_profile.role == "manager" and role_profile.bank_detail:
            bank = role_profile.bank_detail
            bank.bank_name = _strip(form, "bank_name")
            bank.branch = _strip(form, "branch")
            bank.ifsc_code = _strip(form, "ifsc_code").upper()
            bank.account_number = _strip(form, "account_number")
            bank.expiry_date = _strip(form, "expiry_date")
            raw_rent = _strip(form, "rent_per_hour")
            if raw_rent:
                bank.rent_per_hour = float(raw_rent)

        db.session.commit()
        flash(_("Profile updated successfully."), "success")
        return redirect(url_for("my_profile"))

    return render(
        request,
        "my_profile.html",
        role_profile=role_profile,
        property=prop,
        sub_room=sub_room,
        vehicle_types=VEHICLE_TYPES,
        show_sidebar=True,
    )


@router.api_route("/rooms", methods=["GET"], name="my_rooms")
@login_required
async def my_rooms(request: Request):
    role_profiles = (
        RoleProfile.query.filter_by(user_id=session["user_id"]).order_by(RoleProfile.id).all()
    )
    return render(
        request,
        "my_rooms.html",
        role_profiles=role_profiles,
        active_id=session.get("role_profile_id"),
        show_sidebar=True,
    )


@router.api_route("/rooms/switch/{role_profile_id}", methods=["POST"], name="switch_room")
@login_required
async def switch_room(request: Request, role_profile_id: int):
    role_profile = RoleProfile.query.filter_by(
        id=role_profile_id, user_id=session["user_id"]
    ).first()
    if role_profile is None:
        abort(404)

    prop = Property.query.get(role_profile.property_id)
    session["role_profile_id"] = role_profile.id
    session["property_id"] = role_profile.property_id
    session["property_type"] = prop.property_type
    session["sub_room_id"] = role_profile.sub_room_id
    flash(_("Switched to %(name)s.", name=prop.name), "success")
    return redirect(url_for("dashboard"))


@router.api_route("/rooms/join", methods=["POST"], name="join_room")
@login_required
async def join_room(request: Request):
    form = await request.form()
    raw = form.get("invite", "").strip()
    token = raw.rstrip("/").rsplit("/", 1)[-1] if raw else ""
    resolved = resolve_invite_token(token) if token else None

    if not resolved:
        flash(_("This invite link is invalid or has expired."), "danger")
        return redirect(url_for("my_rooms"))

    kind, obj = resolved
    if kind == "property":
        property_id = obj.id
        property_type = obj.property_type
        sub_room_id = None
    else:
        property_id = obj.property_id
        property_type = "office"
        sub_room_id = obj.id

    existing = RoleProfile.query.filter_by(
        user_id=session["user_id"], property_id=property_id
    ).first()
    if existing:
        prop = Property.query.get(property_id)
        session["role_profile_id"] = existing.id
        session["property_id"] = existing.property_id
        session["property_type"] = prop.property_type
        session["sub_room_id"] = existing.sub_room_id
        flash(_("You're already part of %(name)s.", name=prop.name), "info")
        return redirect(url_for("dashboard"))

    session["invite_token"] = token
    session["property_id"] = property_id
    session["property_type"] = property_type
    session["sub_room_id"] = sub_room_id
    return redirect(url_for("role_selection"))
