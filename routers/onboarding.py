"""Onboarding routes: property creation, invite links, role selection and forms."""

from fastapi import APIRouter
from starlette.requests import Request

from constants import (
    OFFICE_ROLES,
    PROPERTY_TYPES,
    RESIDENTIAL_PROPERTY_TYPES,
    RESIDENTIAL_ROLES,
    VEHICLE_TYPES,
)
from database import db
from helpers import (
    REQUIRED_BANK_FIELDS,
    REQUIRED_FIELDS,
    ROLE_TEMPLATES,
    _strip,
    find_duplicate_vehicle_numbers,
    is_duplicate_employee_id,
)
from i18n import _
from models import BankDetail, Property, RoleProfile, SubRoom, Vehicle
from parking_engine import generate_office_parking_slots, generate_parking_slots, link_home_slot
from templating import render
from webcompat import abort, flash, get_or_404, login_required, redirect, session, url_for

router = APIRouter()


# ---------------------------------------------------------------------------
# Form parsers (mirrors app.py helpers)
# ---------------------------------------------------------------------------


def parse_owner_form(form):
    return {
        "name": _strip(form, "name"),
        "phone": _strip(form, "phone"),
        "flat_no": _strip(form, "flat_no"),
        "num_parking_slots": _strip(form, "num_parking_slots"),
        "parking_space_number": _strip(form, "parking_space_number"),
    }


def parse_tenant_form(form):
    return {
        "owner_name": _strip(form, "owner_name"),
        "owner_phone": _strip(form, "owner_phone"),
        "tenant_name": _strip(form, "tenant_name"),
        "tenant_phone": _strip(form, "tenant_phone"),
        "flat_no": _strip(form, "flat_no"),
        "num_parking_slots": _strip(form, "num_parking_slots"),
        "parking_space_number": _strip(form, "parking_space_number"),
    }


def parse_committee_form(form):
    return {
        "head_name": _strip(form, "head_name"),
        "head_phone": _strip(form, "head_phone"),
        "head_flat_no": _strip(form, "head_flat_no"),
        "num_parking_slots": _strip(form, "num_parking_slots"),
        "parking_space_number": _strip(form, "parking_space_number"),
    }


def parse_security_form(form):
    return {
        "name": _strip(form, "name"),
        "phone": _strip(form, "phone"),
        "shift_from": _strip(form, "shift_from"),
        "shift_to": _strip(form, "shift_to"),
    }


def parse_employee_form(form):
    data = {
        "employee_name": _strip(form, "employee_name"),
        "employee_id": _strip(form, "employee_id"),
        "employee_address": _strip(form, "employee_address"),
        "shift_from": _strip(form, "shift_from"),
        "shift_to": _strip(form, "shift_to"),
        "transport": _strip(form, "transport"),
    }
    if data["transport"] == "self":
        data["vehicle_type"] = _strip(form, "vehicle_type")
        data["vehicle_number"] = _strip(form, "vehicle_number").upper()
    return data


def parse_vehicle_table(form):
    types = form.getlist("vehicle_type[]")
    numbers = form.getlist("vehicle_number[]")
    vehicles = []
    s_no = 1
    for vtype, vnum in zip(types, numbers):
        vtype = vtype.strip()
        vnum = vnum.strip().upper()
        if vtype and vnum:
            vehicles.append({"s_no": s_no, "vehicle_type": vtype, "vehicle_number": vnum})
            s_no += 1
    return vehicles


def parse_bank_details(form, role):
    bank = {
        "bank_name": _strip(form, "bank_name"),
        "branch": _strip(form, "branch"),
        "ifsc_code": _strip(form, "ifsc_code").upper(),
        "account_number": _strip(form, "account_number"),
        "expiry_date": _strip(form, "expiry_date"),
        "commission_percent": None,
        "rent_per_hour": None,
    }
    if role == "committee":
        raw = _strip(form, "commission_percent")
        bank["commission_percent"] = float(raw) if raw else 0.0
    if role == "manager":
        raw = _strip(form, "rent_per_hour")
        bank["rent_per_hour"] = float(raw) if raw else 0.0
    return bank


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.api_route("/property-setup", methods=["GET", "POST"], name="property_setup")
@login_required
async def property_setup(request: Request):
    if request.method == "POST":
        form = await request.form()
        property_type = form.get("property_type")
        if property_type not in dict(PROPERTY_TYPES):
            flash(_("Please select a property type."), "danger")
        else:
            session["property_type"] = property_type
            session.pop("property_id", None)
            session.pop("sub_room_id", None)
            if property_type == "office":
                return redirect(url_for("property_form_office"))
            return redirect(url_for("property_form"))

    return render(request, "property_setup.html", property_types=PROPERTY_TYPES)


@router.api_route("/property-form", methods=["GET", "POST"], name="property_form")
@login_required
async def property_form(request: Request):
    if session.get("property_type") not in RESIDENTIAL_PROPERTY_TYPES:
        return redirect(url_for("property_setup"))

    if request.method == "POST":
        form = await request.form()
        property_type = form.get("property_type")
        name = form.get("name", "").strip()
        address = form.get("address", "").strip()
        num_flats = form.get("num_flats", "").strip()
        extra_parking = form.get("extra_parking", "0").strip()

        errors = []
        if property_type not in RESIDENTIAL_PROPERTY_TYPES:
            errors.append(_("Please select Apartment or Gated Community."))
        if not name:
            errors.append(_("Please enter the property name."))
        if not address:
            errors.append(_("Please enter the address."))
        if not num_flats.isdigit():
            errors.append(_("Number of flats must be a number."))
        if extra_parking and not extra_parking.isdigit():
            errors.append(_("Extra parking spaces must be a number."))

        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            prop = Property(
                name=name,
                address=address,
                property_type=property_type,
                num_flats=int(num_flats),
                extra_parking=int(extra_parking or 0),
                created_by=session["user_id"],
            )
            db.session.add(prop)
            db.session.commit()
            generate_parking_slots(prop.id, prop.num_flats + prop.extra_parking)
            session["property_id"] = prop.id
            session["property_type"] = prop.property_type
            session["sub_room_id"] = None
            return redirect(url_for("invite_links"))

    return render(
        request,
        "property_form_residential.html",
        property_type=session.get("property_type"),
        form_data={},
    )


@router.api_route("/property-form/office", methods=["GET", "POST"], name="property_form_office")
@login_required
async def property_form_office(request: Request):
    if session.get("property_type") != "office":
        return redirect(url_for("property_setup"))

    if request.method == "POST":
        form = await request.form()
        name = form.get("name", "").strip()
        address = form.get("address", "").strip()
        company_names = form.getlist("company_name[]")
        num_employees_list = form.getlist("num_employees[]")
        num_parking_list = form.getlist("num_parking_spaces[]")
        floor_alloc_list = form.getlist("floor_allocation[]")
        extra_parking_list = form.getlist("extra_parking[]")

        errors = []
        if not name:
            errors.append(_("Please enter the property name."))
        if not address:
            errors.append(_("Please enter the address."))

        companies = []
        for i, raw_name in enumerate(company_names):
            company_name = raw_name.strip()
            if not company_name:
                continue
            try:
                num_employees = int(num_employees_list[i]) if num_employees_list[i].strip() else None
                num_parking = int(num_parking_list[i]) if num_parking_list[i].strip() else None
                extra = int(extra_parking_list[i]) if extra_parking_list[i].strip() else 0
            except (ValueError, IndexError):
                errors.append(_("Please enter valid numbers for company '%(name)s'.", name=company_name))
                continue
            companies.append(
                {
                    "company_name": company_name,
                    "num_employees": num_employees,
                    "num_parking_spaces": num_parking,
                    "floor_allocation": floor_alloc_list[i].strip() if i < len(floor_alloc_list) else "",
                    "extra_parking": extra,
                }
            )

        if not companies:
            errors.append(_("Please add at least one company."))

        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            prop = Property(
                name=name,
                address=address,
                property_type="office",
                created_by=session["user_id"],
            )
            db.session.add(prop)
            db.session.flush()
            for company in companies:
                sub_room = SubRoom(property_id=prop.id, **company)
                db.session.add(sub_room)
                db.session.flush()
                generate_office_parking_slots(prop.id, sub_room)
            db.session.commit()
            session["property_id"] = prop.id
            session["property_type"] = "office"
            session["sub_room_id"] = None
            return redirect(url_for("invite_links"))

    return render(request, "property_form_office.html", form_data={})


@router.api_route("/invite-links", methods=["GET"], name="invite_links")
@login_required
async def invite_links(request: Request):
    property_id = session.get("property_id")
    if not property_id:
        return redirect(url_for("property_setup"))

    prop = get_or_404(Property, property_id)
    invite_url = url_for("join", token=prop.invite_token, _external=True)
    sub_room_links = [
        (sub_room, url_for("join", token=sub_room.invite_token, _external=True))
        for sub_room in prop.sub_rooms
    ]
    onboarding = (
        RoleProfile.query.filter_by(
            user_id=session["user_id"], property_id=property_id
        ).first()
        is None
    )

    return render(
        request,
        "invite_links.html",
        property=prop,
        invite_url=invite_url,
        sub_room_links=sub_room_links,
        sub_rooms=prop.sub_rooms,
        onboarding=onboarding,
        show_sidebar=not onboarding,
    )


@router.api_route("/invite-links/next", methods=["GET", "POST"], name="invite_links_next")
@login_required
async def invite_links_next(request: Request):
    property_id = session.get("property_id")
    if not property_id:
        return redirect(url_for("property_setup"))

    prop = get_or_404(Property, property_id)
    if request.method == "POST" and prop.property_type == "office":
        form = await request.form()
        sub_room_id = form.get("sub_room_id")
        try:
            sub_room_id = int(sub_room_id)
        except (TypeError, ValueError):
            sub_room_id = None
        valid_ids = {sub_room.id for sub_room in prop.sub_rooms}
        if sub_room_id not in valid_ids:
            flash(_("Please select your company to continue."), "danger")
            return redirect(url_for("invite_links"))
        session["sub_room_id"] = sub_room_id

    return redirect(url_for("role_selection"))


@router.api_route("/role-selection", methods=["GET", "POST"], name="role_selection")
@login_required
async def role_selection(request: Request):
    property_id = session.get("property_id")
    if not property_id:
        return redirect(url_for("property_setup"))

    prop = get_or_404(Property, property_id)
    roles = RESIDENTIAL_ROLES if prop.property_type in RESIDENTIAL_PROPERTY_TYPES else OFFICE_ROLES
    sub_room = SubRoom.query.get(session["sub_room_id"]) if session.get("sub_room_id") else None

    if request.method == "POST":
        form = await request.form()
        role = form.get("role")
        if role not in dict(roles):
            flash(_("Please select a role."), "danger")
        else:
            session["selected_role"] = role
            return redirect(url_for("role_form", role=role))

    return render(request, "role_selection.html", roles=roles, property=prop, sub_room=sub_room)


@router.api_route("/role-form/{role}", methods=["GET", "POST"], name="role_form")
@login_required
async def role_form(request: Request, role: str):
    property_id = session.get("property_id")
    if not property_id:
        return redirect(url_for("property_setup"))

    prop = get_or_404(Property, property_id)
    sub_room_id = session.get("sub_room_id")
    sub_room = SubRoom.query.get(sub_room_id) if sub_room_id else None

    allowed_roles = dict(RESIDENTIAL_ROLES if prop.property_type in RESIDENTIAL_PROPERTY_TYPES else OFFICE_ROLES)
    if role not in allowed_roles:
        abort(404)

    form_data = {}
    if request.method == "POST":
        form = await request.form()
        form_data = form
        vehicles = []
        bank = None

        if role == "owner":
            data = parse_owner_form(form)
            vehicles = parse_vehicle_table(form)
            bank = parse_bank_details(form, role)
        elif role == "tenant":
            data = parse_tenant_form(form)
            vehicles = parse_vehicle_table(form)
            bank = parse_bank_details(form, role)
        elif role == "committee":
            data = parse_committee_form(form)
            vehicles = parse_vehicle_table(form)
            bank = parse_bank_details(form, role)
        elif role == "security":
            data = parse_security_form(form)
        else:
            data = parse_employee_form(form)
            if role == "manager":
                bank = parse_bank_details(form, role)

        errors = []
        for field in REQUIRED_FIELDS[role]:
            if not data.get(field):
                errors.append(_("Please fill in all required fields."))
                break

        if role in ("employee", "manager") and data.get("transport") == "self":
            if not data.get("vehicle_type") or not data.get("vehicle_number"):
                errors.append(_("Please enter your vehicle type and number for self-transport."))

        if bank is not None:
            for field in REQUIRED_BANK_FIELDS:
                if not bank.get(field):
                    errors.append(_("Please fill in all required bank details."))
                    break

        if role in ("owner", "tenant", "committee") and not vehicles:
            errors.append(_("Please add at least one vehicle."))

        if vehicles:
            duplicates = find_duplicate_vehicle_numbers(property_id, [v["vehicle_number"] for v in vehicles])
            if duplicates:
                errors.append(
                    _("Vehicle number(s) already registered to another member: %(numbers)s",
                      numbers=", ".join(duplicates))
                )

        if role in ("employee", "manager") and data.get("transport") == "self":
            duplicates = find_duplicate_vehicle_numbers(property_id, [data["vehicle_number"]])
            if duplicates:
                errors.append(
                    _("Vehicle number %(number)s is already registered to another member.",
                      number=duplicates[0])
                )

        if role in ("employee", "manager") and is_duplicate_employee_id(
            property_id, sub_room_id, data.get("employee_id")
        ):
            errors.append(_("This Employee ID is already registered."))

        if not errors:
            role_profile = RoleProfile(
                user_id=session["user_id"],
                property_id=property_id,
                sub_room_id=sub_room_id,
                role=role,
                data=data,
            )
            db.session.add(role_profile)
            db.session.flush()

            for vehicle in vehicles:
                db.session.add(Vehicle(role_profile_id=role_profile.id, **vehicle))

            if bank is not None:
                db.session.add(BankDetail(role_profile_id=role_profile.id, **bank))

            db.session.commit()

            if role in ("owner", "tenant", "committee"):
                link_home_slot(role_profile, data.get("parking_space_number"))

            session["role_profile_id"] = role_profile.id
            session.pop("invite_token", None)
            return redirect(url_for("dashboard"))

        for error in errors:
            flash(error, "danger")

    return render(
        request,
        ROLE_TEMPLATES[role],
        property=prop,
        sub_room=sub_room,
        vehicle_types=VEHICLE_TYPES,
        form_data=form_data,
    )
