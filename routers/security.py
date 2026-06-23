"""Security guard routes: QR scan, visitor/transport entry/exit, unexpected visitors."""

from datetime import timedelta

from fastapi import APIRouter
from starlette.requests import Request

from constants import RESIDENTIAL_PROPERTY_TYPES, VEHICLE_TYPES
from database import db
from helpers import (
    PHONE_REGEX,
    _parse_date,
    _parse_time,
    _require_role_profile,
    _role_profile_label,
    _strip,
)
from i18n import _
from models import Property, RoleProfile, TransportRequest, VisitorRequest
from parking_engine import notify, now_ist
from templating import render
from webcompat import abort, first_or_404, flash, login_required, redirect, url_for

router = APIRouter()


@router.api_route("/security/scan", methods=["GET", "POST"], name="security_scan")
@login_required
async def security_scan(request: Request):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role != "security":
        abort(403)

    if request.method == "POST":
        form = await request.form()
        token = _strip(form, "token").rstrip("/").rsplit("/", 1)[-1]
        if VisitorRequest.query.filter_by(
            qr_token=token, property_id=role_profile.property_id
        ).first():
            return redirect(url_for("security_visitor", token=token))
        if TransportRequest.query.filter_by(
            qr_token=token, property_id=role_profile.property_id
        ).first():
            return redirect(url_for("security_transport", token=token))
        flash(_("No pass found for that code."), "danger")
        return redirect(url_for("security_scan"))

    return render(request, "security_scan.html", role_profile=role_profile, show_sidebar=True)


@router.api_route("/security/visitor/{token}", methods=["GET"], name="security_visitor")
@login_required
async def security_visitor(request: Request, token: str):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role != "security":
        abort(403)

    vr = first_or_404(
        VisitorRequest.query.filter_by(qr_token=token, property_id=role_profile.property_id)
    )
    slot = vr.slot_availability.parking_slot if vr.slot_availability else vr.parking_slot

    return render(
        request,
        "security_visitor.html",
        role_profile=role_profile,
        visitor_request=vr,
        slot=slot,
        role_profile_label=_role_profile_label,
        show_sidebar=True,
    )


@router.api_route(
    "/security/visitor/{token}/entry", methods=["POST"], name="security_visitor_entry"
)
@login_required
async def security_visitor_entry(request: Request, token: str):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role != "security":
        abort(403)

    vr = first_or_404(
        VisitorRequest.query.filter_by(qr_token=token, property_id=role_profile.property_id)
    )
    if vr.status != "allocated":
        flash(_("This visitor cannot be marked as entered right now."), "warning")
        return redirect(url_for("security_visitor", token=token))

    vr.status = "entered"
    vr.entry_time = now_ist()
    db.session.commit()
    flash(_("%(name)s marked as entered.", name=vr.visitor_name), "success")
    return redirect(url_for("security_visitor", token=token))


@router.api_route("/security/visitor/{token}/exit", methods=["POST"], name="security_visitor_exit")
@login_required
async def security_visitor_exit(request: Request, token: str):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role != "security":
        abort(403)

    vr = first_or_404(
        VisitorRequest.query.filter_by(qr_token=token, property_id=role_profile.property_id)
    )
    if vr.status != "entered":
        flash(_("This visitor cannot be marked as exited right now."), "warning")
        return redirect(url_for("security_visitor", token=token))

    vr.status = "exited"
    vr.exit_time = now_ist()
    db.session.commit()
    flash(_("%(name)s marked as exited.", name=vr.visitor_name), "success")
    return redirect(url_for("security_visitor", token=token))


@router.api_route("/security/transport/{token}", methods=["GET"], name="security_transport")
@login_required
async def security_transport(request: Request, token: str):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role != "security":
        abort(403)

    tr = first_or_404(
        TransportRequest.query.filter_by(qr_token=token, property_id=role_profile.property_id)
    )

    return render(
        request,
        "security_transport.html",
        role_profile=role_profile,
        transport_request=tr,
        show_sidebar=True,
    )


@router.api_route(
    "/security/transport/{token}/entry", methods=["POST"], name="security_transport_entry"
)
@login_required
async def security_transport_entry(request: Request, token: str):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role != "security":
        abort(403)

    tr = first_or_404(
        TransportRequest.query.filter_by(qr_token=token, property_id=role_profile.property_id)
    )
    if tr.status != "allocated":
        flash(_("This pass cannot be marked as entered right now."), "warning")
        return redirect(url_for("security_transport", token=token))

    tr.status = "entered"
    tr.entry_time = now_ist()
    db.session.commit()
    flash(_("Marked as entered."), "success")
    return redirect(url_for("security_transport", token=token))


@router.api_route(
    "/security/transport/{token}/exit", methods=["POST"], name="security_transport_exit"
)
@login_required
async def security_transport_exit(request: Request, token: str):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role != "security":
        abort(403)

    tr = first_or_404(
        TransportRequest.query.filter_by(qr_token=token, property_id=role_profile.property_id)
    )
    if tr.status != "entered":
        flash(_("This pass cannot be marked as exited right now."), "warning")
        return redirect(url_for("security_transport", token=token))

    tr.status = "exited"
    tr.exit_time = now_ist()
    db.session.commit()
    flash(_("Marked as exited."), "success")
    return redirect(url_for("security_transport", token=token))


@router.api_route(
    "/security/unexpected-visitor", methods=["GET", "POST"], name="unexpected_visitor"
)
@login_required
async def unexpected_visitor(request: Request):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role != "security":
        abort(403)

    prop = Property.query.get(role_profile.property_id)
    is_office = prop.property_type not in RESIDENTIAL_PROPERTY_TYPES
    host_roles = ("employee", "manager") if is_office else ("owner", "tenant", "committee")

    hosts = RoleProfile.query.filter(
        RoleProfile.property_id == role_profile.property_id,
        RoleProfile.role.in_(host_roles),
    ).all()

    form_data = {}
    if request.method == "POST":
        form = await request.form()
        form_data = form
        visitor_name = _strip(form, "visitor_name")
        visitor_phone = _strip(form, "visitor_phone")
        vehicle_type = _strip(form, "vehicle_type")
        vehicle_number = _strip(form, "vehicle_number").upper()
        purpose = _strip(form, "purpose")
        date_str = _strip(form, "date")
        host_id = _strip(form, "host_role_profile_id")
        more_than_1hr = form.get("more_than_1hr") == "on"

        errors = []
        if not visitor_name:
            errors.append(_("Please enter the visitor's name."))
        if not PHONE_REGEX.match(visitor_phone):
            errors.append(_("Please enter a valid 10-digit visitor phone number."))
        if vehicle_type not in VEHICLE_TYPES:
            errors.append(_("Please select a vehicle type."))
        if not vehicle_number:
            errors.append(_("Please enter the vehicle number."))
        if not date_str:
            errors.append(_("Please select a date."))

        host = RoleProfile.query.get(int(host_id)) if host_id.isdigit() else None
        if not host or host.property_id != role_profile.property_id or host.role not in host_roles:
            errors.append(_("Please select who the visitor is here to see."))

        date_val = _parse_date(date_str) if date_str else None
        from_time = to_time = None

        if more_than_1hr:
            from_str = _strip(form, "from_time")
            to_str = _strip(form, "to_time")
            if not from_str or not to_str:
                errors.append(_("Please enter the from and to time."))
            else:
                from_time = _parse_time(from_str)
                to_time = _parse_time(to_str)
        elif not errors:
            now = now_ist()
            date_val = now.date()
            from_time = now.time().replace(second=0, microsecond=0)
            to_time = (now + timedelta(hours=1)).time().replace(second=0, microsecond=0)

        if not errors:
            # `host`/`from_time`/`to_time` are only unset when one of the checks
            # above already appended an error, so `errors` would be non-empty.
            # Type-narrowing aid only, not a security boundary.
            assert host is not None  # nosec B101
            assert from_time is not None  # nosec B101
            assert to_time is not None  # nosec B101
            vr = VisitorRequest(
                property_id=role_profile.property_id,
                host_role_profile_id=host.id,
                visitor_name=visitor_name,
                visitor_phone=visitor_phone,
                vehicle_type=vehicle_type,
                vehicle_number=vehicle_number,
                date=date_val,
                from_time=from_time,
                to_time=to_time,
                purpose=purpose or None,
                is_unexpected=True,
                created_by_role_profile_id=role_profile.id,
                status="pending_approval",
            )
            db.session.add(vr)
            db.session.flush()

            notify_ids = {host.id}
            if host.sub_room_id:
                notify_ids.update(
                    rp.id
                    for rp in RoleProfile.query.filter(
                        RoleProfile.property_id == role_profile.property_id,
                        RoleProfile.sub_room_id == host.sub_room_id,
                        RoleProfile.role == "manager",
                    ).all()
                )
            for notify_id in notify_ids:
                notify(
                    notify_id,
                    "Unexpected visitor needs approval",
                    f"Security logged a walk-in visitor {visitor_name} ({visitor_phone}), "
                    f"{vehicle_type} {vehicle_number}, on {date_val} from "
                    f"{from_time.strftime('%H:%M')} to {to_time.strftime('%H:%M')}"
                    f"{' for: ' + purpose if purpose else ''}. Please approve or deny.",
                    link=url_for("notifications"),
                )
            db.session.commit()
            flash(_("Visitor logged. Waiting for resident approval."), "success")
            return redirect(url_for("unexpected_visitor"))

        for error in errors:
            flash(error, "danger")

    recent = (
        VisitorRequest.query.filter_by(
            property_id=role_profile.property_id,
            is_unexpected=True,
            created_by_role_profile_id=role_profile.id,
        )
        .order_by(VisitorRequest.created_at.desc())
        .limit(20)
        .all()
    )

    return render(
        request,
        "unexpected_visitor.html",
        role_profile=role_profile,
        hosts=hosts,
        recent=recent,
        vehicle_types=VEHICLE_TYPES,
        form_data=form_data,
        role_profile_label=_role_profile_label,
        today=now_ist().date().isoformat(),
        show_sidebar=True,
    )
