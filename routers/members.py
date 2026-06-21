"""Members list, remove, and CSV export routes."""

import csv
import io

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import Response

from constants import RESIDENTIAL_PROPERTY_TYPES
from database import db
from helpers import _require_role_profile, _role_profile_label
from i18n import _
from models import Notification, ParkingSlot, Property, RoleProfile, SlotAvailability
from templating import render
from webcompat import abort, flash, login_required, redirect, url_for

router = APIRouter()


@router.api_route("/members", methods=["GET"], name="members")
@login_required
async def members(request: Request):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    prop = Property.query.get(role_profile.property_id)
    is_office = prop.property_type not in RESIDENTIAL_PROPERTY_TYPES

    profile_query = RoleProfile.query.filter_by(property_id=role_profile.property_id)
    if is_office:
        profile_query = profile_query.filter_by(sub_room_id=role_profile.sub_room_id)
    profiles = profile_query.order_by(RoleProfile.role, RoleProfile.id).all()

    return render(
        request,
        "members.html",
        role_profile=role_profile,
        property=prop,
        profiles=profiles,
        can_remove=role_profile.role in ("owner", "committee", "manager"),
        show_sidebar=True,
    )


@router.api_route("/members/{member_id}/remove", methods=["POST"], name="remove_member")
@login_required
async def remove_member(request: Request, member_id: int):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role not in ("owner", "committee", "manager"):
        abort(403)

    member = RoleProfile.query.get(member_id)
    if member is None:
        abort(404)
    if member.property_id != role_profile.property_id:
        abort(404)
    if role_profile.role == "manager" and member.sub_room_id != role_profile.sub_room_id:
        abort(404)
    if member.id == role_profile.id:
        flash(_("You cannot remove yourself."), "danger")
        return redirect(url_for("members"))

    for slot in ParkingSlot.query.filter_by(home_role_profile_id=member.id).all():
        slot.home_role_profile_id = None
    Notification.query.filter_by(role_profile_id=member.id).delete()
    SlotAvailability.query.filter_by(role_profile_id=member.id).delete()

    db.session.delete(member)
    db.session.commit()
    flash(_("Member removed."), "success")
    return redirect(url_for("members"))


@router.api_route("/members/export.csv", methods=["GET"], name="export_members_csv")
@login_required
async def export_members_csv(request: Request):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    prop = Property.query.get(role_profile.property_id)
    is_office = prop.property_type not in RESIDENTIAL_PROPERTY_TYPES

    profile_query = RoleProfile.query.filter_by(property_id=role_profile.property_id)
    if is_office:
        profile_query = profile_query.filter_by(sub_room_id=role_profile.sub_room_id)
    profiles = profile_query.order_by(RoleProfile.role, RoleProfile.id).all()

    output = io.StringIO()
    writer = csv.writer(output)
    if is_office:
        writer.writerow(["Name", "Role", "Employee ID", "Contact", "Shift From", "Shift To"])
        for p in profiles:
            d = p.data or {}
            name = d.get("name") or d.get("employee_name") or "-"
            writer.writerow([
                name, p.role, d.get("employee_id", "-"), p.user.contact or "-",
                d.get("shift_from", "-"), d.get("shift_to", "-"),
            ])
    else:
        writer.writerow(["Name", "Role", "Flat / Unit", "Contact", "Vehicles"])
        for p in profiles:
            d = p.data or {}
            name = d.get("name") or d.get("tenant_name") or d.get("head_name") or "-"
            flat = d.get("flat_no") or d.get("head_flat_no") or "-"
            vehicles = ", ".join(v.vehicle_number for v in p.vehicles) or "-"
            writer.writerow([name, p.role, flat, p.user.contact or "-", vehicles])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=members.csv"},
    )
