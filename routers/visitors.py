"""Visitor request, visitor log (with CSV export), visitor pass, and QR image routes."""

import csv
import io

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from starlette.requests import Request
from starlette.responses import Response

from constants import VEHICLE_TYPES
from database import db
from helpers import (
    PHONE_REGEX,
    _parse_date,
    _parse_time,
    _require_role_profile,
    _role_profile_label,
    _strip,
    _visitor_log_query,
)
from i18n import _
from models import Property, VisitorRequest
from parking_engine import REQUEST_STATUS_CLASSES, REQUEST_STATUS_LABELS, try_match_request
from templating import render
from webcompat import abort, first_or_404, flash, login_required, redirect, url_for

try:
    import qrcode
except ImportError:
    qrcode = None

router = APIRouter()


@router.api_route("/visitor-request", methods=["GET", "POST"], name="visitor_request")
@login_required
async def visitor_request(request: Request):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role not in ("owner", "tenant", "committee"):
        abort(403)

    form_data = {}
    if request.method == "POST":
        form = await request.form()
        form_data = form
        visitor_name = _strip(form, "visitor_name")
        visitor_phone = _strip(form, "visitor_phone")
        vehicle_type = _strip(form, "vehicle_type")
        vehicle_number = _strip(form, "vehicle_number").upper()
        date_str = _strip(form, "date")
        from_str = _strip(form, "from_time")
        to_str = _strip(form, "to_time")

        errors = []
        if not visitor_name:
            errors.append(_("Please enter the visitor's name."))
        if not PHONE_REGEX.match(visitor_phone):
            errors.append(_("Please enter a valid 10-digit visitor phone number."))
        if vehicle_type not in VEHICLE_TYPES:
            errors.append(_("Please select a vehicle type."))
        if not vehicle_number:
            errors.append(_("Please enter the vehicle number."))
        if not date_str or not from_str or not to_str:
            errors.append(_("Please fill in date, from time and to time."))

        if not errors:
            vr = VisitorRequest(
                property_id=role_profile.property_id,
                host_role_profile_id=role_profile.id,
                visitor_name=visitor_name,
                visitor_phone=visitor_phone,
                vehicle_type=vehicle_type,
                vehicle_number=vehicle_number,
                date=_parse_date(date_str),
                from_time=_parse_time(from_str),
                to_time=_parse_time(to_str),
                status="pending_allocation",
            )
            db.session.add(vr)
            db.session.flush()
            try_match_request(vr)
            db.session.commit()
            if vr.status == "allocated":
                flash(_("Visitor request created and a parking slot was allocated!"), "success")
            else:
                flash(
                    _("Visitor request created. We'll notify you once a slot is available."), "info"
                )
            return redirect(url_for("visitor_request"))

        for error in errors:
            flash(error, "danger")

    requests_ = (
        VisitorRequest.query.filter_by(host_role_profile_id=role_profile.id)
        .order_by(VisitorRequest.date.desc(), VisitorRequest.from_time.desc())
        .all()
    )

    return render(
        request,
        "visitor_request.html",
        role_profile=role_profile,
        requests=requests_,
        vehicle_types=VEHICLE_TYPES,
        form_data=form_data,
        show_sidebar=True,
    )


@router.api_route("/visitor-log", methods=["GET"], name="visitor_log")
@login_required
async def visitor_log(request: Request):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role not in ("owner", "committee", "manager", "security"):
        abort(403)

    prop = Property.query.get(role_profile.property_id)
    query = _visitor_log_query(role_profile, prop)

    search = request.query_params.get("q", "").strip()
    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(
                VisitorRequest.visitor_name.ilike(like),
                VisitorRequest.vehicle_number.ilike(like),
                VisitorRequest.visitor_phone.ilike(like),
            )
        )

    status_filter = request.query_params.get("status", "").strip()
    if status_filter:
        query = query.filter(VisitorRequest.status == status_filter)

    records = (
        query.order_by(VisitorRequest.date.desc(), VisitorRequest.from_time.desc()).limit(500).all()
    )

    return render(
        request,
        "visitor_log.html",
        role_profile=role_profile,
        property=prop,
        records=records,
        search=search,
        status_filter=status_filter,
        status_options=REQUEST_STATUS_LABELS,
        status_classes=REQUEST_STATUS_CLASSES,
        role_profile_label=_role_profile_label,
        show_sidebar=True,
    )


@router.api_route("/visitor-log/export.csv", methods=["GET"], name="export_visitor_log_csv")
@login_required
async def export_visitor_log_csv(request: Request):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role not in ("owner", "committee", "manager", "security"):
        abort(403)

    prop = Property.query.get(role_profile.property_id)
    records = (
        _visitor_log_query(role_profile, prop)
        .order_by(VisitorRequest.date.desc(), VisitorRequest.from_time.desc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Date",
            "Visitor Name",
            "Phone",
            "Vehicle Type",
            "Vehicle Number",
            "From",
            "To",
            "Purpose",
            "Host",
            "Status",
            "Entry Time",
            "Exit Time",
        ]
    )
    for r in records:
        writer.writerow(
            [
                r.date.isoformat(),
                r.visitor_name,
                r.visitor_phone,
                r.vehicle_type,
                r.vehicle_number,
                r.from_time.strftime("%H:%M"),
                r.to_time.strftime("%H:%M"),
                r.purpose or "-",
                _role_profile_label(r.host_role_profile),
                str(REQUEST_STATUS_LABELS.get(r.status, r.status)),
                r.entry_time.strftime("%Y-%m-%d %H:%M") if r.entry_time else "-",
                r.exit_time.strftime("%Y-%m-%d %H:%M") if r.exit_time else "-",
            ]
        )

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=visitor_log.csv"},
    )


@router.api_route("/visitor-pass/{token}", methods=["GET"], name="visitor_pass")
async def visitor_pass(request: Request, token: str):
    vr = first_or_404(VisitorRequest.query.filter_by(qr_token=token))
    slot = vr.slot_availability.parking_slot if vr.slot_availability else vr.parking_slot

    return render(
        request,
        "visitor_pass.html",
        visitor_request=vr,
        slot=slot,
    )


@router.api_route("/qr/{token}.png", methods=["GET"], name="qr_image")
async def qr_image(request: Request, token: str):
    vr = first_or_404(VisitorRequest.query.filter_by(qr_token=token))
    # Host header is validated by TrustedHostMiddleware; see main.py.
    pass_url = url_for("visitor_pass", token=vr.qr_token, _external=True)  # nosemgrep

    img = qrcode.make(pass_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")
