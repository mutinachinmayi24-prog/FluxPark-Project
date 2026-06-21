"""Notifications, visitor approval/denial, and mark-read routes."""

from fastapi import APIRouter
from starlette.requests import Request

from constants import RESIDENTIAL_PROPERTY_TYPES
from database import db
from helpers import (
    _approvable_host_ids,
    _require_role_profile,
    _role_profile_label,
)
from i18n import _
from models import Notification, Property, RoleProfile, VisitorRequest
from parking_engine import allocate_unexpected_visitor, notify, try_match_request
from templating import render
from webcompat import abort, flash, login_required, redirect, url_for

router = APIRouter()


@router.api_route("/notifications", methods=["GET"], name="notifications")
@login_required
async def notifications(request: Request):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    items = (
        Notification.query.filter_by(role_profile_id=role_profile.id)
        .order_by(Notification.created_at.desc())
        .all()
    )

    pending_requests = []
    if role_profile.role in ("owner", "tenant", "committee", "employee", "manager"):
        pending_requests = (
            VisitorRequest.query.filter(
                VisitorRequest.host_role_profile_id.in_(_approvable_host_ids(role_profile)),
                VisitorRequest.status == "pending_approval",
            )
            .order_by(VisitorRequest.date, VisitorRequest.from_time)
            .all()
        )

    return render(
        request,
        "notifications.html",
        role_profile=role_profile,
        notifications=items,
        pending_requests=pending_requests,
        role_profile_label=_role_profile_label,
        show_sidebar=True,
    )


@router.api_route(
    "/notifications/{notification_id}/read",
    methods=["POST"],
    name="mark_notification_read",
)
@login_required
async def mark_notification_read(request: Request, notification_id: int):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    notification = Notification.query.get(notification_id)
    if notification is None:
        abort(404)
    if notification.role_profile_id != role_profile.id:
        abort(403)
    notification.is_read = True
    db.session.commit()
    return redirect(url_for("notifications"))


@router.api_route(
    "/notifications/mark-all-read",
    methods=["POST"],
    name="mark_all_notifications_read",
)
@login_required
async def mark_all_notifications_read(request: Request):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    Notification.query.filter_by(role_profile_id=role_profile.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return redirect(url_for("notifications"))


@router.api_route(
    "/visitor-requests/{request_id}/approve",
    methods=["POST"],
    name="approve_visitor_request",
)
@login_required
async def approve_visitor_request(request: Request, request_id: int):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    vr = VisitorRequest.query.get(request_id)
    if vr is None:
        abort(404)
    if vr.host_role_profile_id not in _approvable_host_ids(role_profile):
        abort(403)
    if vr.status != "pending_approval":
        flash(_("This request has already been processed."), "warning")
        return redirect(url_for("notifications"))

    vr.status = "pending_allocation"
    db.session.flush()
    prop = Property.query.get(vr.property_id)
    if prop.property_type in RESIDENTIAL_PROPERTY_TYPES:
        try_match_request(vr)
    else:
        allocate_unexpected_visitor(vr)
    db.session.commit()
    if vr.status == "allocated":
        flash(_("Approved %(name)s and allocated a parking slot.", name=vr.visitor_name), "success")
    else:
        flash(_("Approved %(name)s. We'll notify you once a slot is available.", name=vr.visitor_name), "info")
    return redirect(url_for("notifications"))


@router.api_route(
    "/visitor-requests/{request_id}/deny",
    methods=["POST"],
    name="deny_visitor_request",
)
@login_required
async def deny_visitor_request(request: Request, request_id: int):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    vr = VisitorRequest.query.get(request_id)
    if vr is None:
        abort(404)
    if vr.host_role_profile_id not in _approvable_host_ids(role_profile):
        abort(403)
    if vr.status != "pending_approval":
        flash(_("This request has already been processed."), "warning")
        return redirect(url_for("notifications"))

    vr.status = "rejected"
    if vr.created_by_role_profile_id:
        notify(
            vr.created_by_role_profile_id,
            "Unexpected visitor denied",
            f"{_role_profile_label(role_profile)} denied entry for visitor {vr.visitor_name} "
            f"({vr.visitor_phone}).",
        )
    db.session.commit()
    flash(_("Denied entry for %(name)s.", name=vr.visitor_name), "info")
    return redirect(url_for("notifications"))
