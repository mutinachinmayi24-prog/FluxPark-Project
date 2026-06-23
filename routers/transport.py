"""Transport request, transport pass, and QR image routes (office employees/managers)."""

import io
from datetime import timedelta

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from starlette.requests import Request

from constants import VEHICLE_TYPES
from database import db
from helpers import (
    TRANSPORT_REQUEST_CUTOFF,
    _parse_time,
    _require_role_profile,
    _strip,
)
from i18n import _
from models import TransportRequest
from parking_engine import now_ist, run_pending_transport_allocations
from templating import render
from webcompat import abort, first_or_404, flash, login_required, redirect, url_for

try:
    import qrcode
except ImportError:
    qrcode = None

router = APIRouter()


@router.api_route("/transport-request", methods=["GET", "POST"], name="transport_request")
@login_required
async def transport_request(request: Request):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role not in ("employee", "manager"):
        abort(403)

    now_dt = now_ist()
    tomorrow = now_dt.date() + timedelta(days=1)
    cutoff_passed = now_dt.time() >= TRANSPORT_REQUEST_CUTOFF

    run_pending_transport_allocations(role_profile.property_id, now_dt)

    existing = TransportRequest.query.filter_by(
        role_profile_id=role_profile.id, date=tomorrow
    ).first()

    form_data = {}
    if request.method == "POST":
        form = await request.form()
        form_data = form
        action = _strip(form, "action")

        if action == "cancel":
            if not existing or existing.status != "pending_allocation":
                flash(_("There's no pending request for tomorrow to cancel."), "warning")
            elif cutoff_passed:
                flash(
                    _("The 9 PM cutoff has passed; this request can no longer be changed."),
                    "danger",
                )
            else:
                db.session.delete(existing)
                db.session.commit()
                flash(_("Transport request for tomorrow cancelled."), "info")
            return redirect(url_for("transport_request"))

        if existing:
            flash(_("You've already submitted a transport request for tomorrow."), "warning")
            return redirect(url_for("transport_request"))
        if cutoff_passed:
            flash(
                _("Requests for tomorrow's parking must be submitted before 9 PM today."), "danger"
            )
            return redirect(url_for("transport_request"))

        vehicle_type = _strip(form, "vehicle_type")
        vehicle_number = _strip(form, "vehicle_number").upper()
        from_str = _strip(form, "from_time")
        to_str = _strip(form, "to_time")

        errors = []
        if vehicle_type not in VEHICLE_TYPES:
            errors.append(_("Please select a vehicle type."))
        if not vehicle_number:
            errors.append(_("Please enter the vehicle number."))
        if not from_str or not to_str:
            errors.append(_("Please fill in your shift start and end time."))

        if not errors:
            tr = TransportRequest(
                role_profile_id=role_profile.id,
                property_id=role_profile.property_id,
                sub_room_id=role_profile.sub_room_id,
                date=tomorrow,
                vehicle_type=vehicle_type,
                vehicle_number=vehicle_number,
                from_time=_parse_time(from_str),
                to_time=_parse_time(to_str),
                status="pending_allocation",
            )
            db.session.add(tr)
            db.session.commit()
            flash(
                _(
                    "Transport request for tomorrow submitted. Slots are allocated after the 9 PM cutoff."
                ),
                "success",
            )
            return redirect(url_for("transport_request"))

        for error in errors:
            flash(error, "danger")

    history = (
        TransportRequest.query.filter_by(role_profile_id=role_profile.id)
        .order_by(TransportRequest.date.desc())
        .limit(14)
        .all()
    )

    data = role_profile.data or {}
    defaults = {
        "vehicle_type": data.get("vehicle_type", ""),
        "vehicle_number": data.get("vehicle_number", ""),
        "from_time": data.get("shift_from", ""),
        "to_time": data.get("shift_to", ""),
    }

    return render(
        request,
        "transport_request.html",
        role_profile=role_profile,
        tomorrow=tomorrow,
        existing=existing,
        cutoff_passed=cutoff_passed,
        history=history,
        vehicle_types=VEHICLE_TYPES,
        defaults=defaults,
        form_data=form_data,
        show_sidebar=True,
    )


@router.api_route("/transport-pass/{token}", methods=["GET"], name="transport_pass")
async def transport_pass(request: Request, token: str):
    tr = first_or_404(TransportRequest.query.filter_by(qr_token=token))

    return render(
        request,
        "transport_pass.html",
        transport_request=tr,
    )


@router.api_route("/transport-qr/{token}.png", methods=["GET"], name="transport_qr_image")
async def transport_qr_image(request: Request, token: str):
    tr = first_or_404(TransportRequest.query.filter_by(qr_token=token))
    pass_url = url_for("transport_pass", token=tr.qr_token, _external=True)

    img = qrcode.make(pass_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")
