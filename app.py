import os
import re
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

from constants import (
    OFFICE_ROLES,
    OTP_VALIDITY_MINUTES,
    PROPERTY_TYPES,
    RESIDENTIAL_PROPERTY_TYPES,
    RESIDENTIAL_ROLES,
    VEHICLE_TYPES,
)
from extensions import db
from models import BankDetail, OTPRequest, Property, RoleProfile, SubRoom, User, Vehicle

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    db.create_all()

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("signup"))
        return view(*args, **kwargs)

    return wrapped


def mask_contact(contact, contact_type):
    if contact_type == "email":
        local, _, domain = contact.partition("@")
        if len(local) <= 2:
            masked_local = local[0] + "*" * max(len(local) - 1, 1)
        else:
            masked_local = local[:2] + "*" * (len(local) - 2)
        return f"{masked_local}@{domain}"
    return f"{'*' * 6}{contact[-4:]}"


def create_and_send_otp(contact):
    code = f"{secrets.randbelow(10 ** 6):06d}"
    expires_at = datetime.utcnow() + timedelta(minutes=OTP_VALIDITY_MINUTES)
    otp = OTPRequest(contact=contact, code=code, expires_at=expires_at)
    db.session.add(otp)
    db.session.commit()
    # Mock delivery for now: shown on screen instead of a real email/SMS provider.
    flash(
        f"Demo mode: your verification code is {code} (valid for {OTP_VALIDITY_MINUTES} minutes).",
        "info",
    )
    return otp


def find_or_create_user(contact_type, contact):
    filters = {"email": contact} if contact_type == "email" else {"phone": contact}
    user = User.query.filter_by(**filters).first()
    if user is None:
        user = User(**filters)
        db.session.add(user)
        db.session.commit()
    return user


def resolve_invite_token(token):
    prop = Property.query.filter_by(invite_token=token).first()
    if prop:
        return "property", prop
    sub_room = SubRoom.query.filter_by(invite_token=token).first()
    if sub_room:
        return "sub_room", sub_room
    return None


def route_after_login(user):
    if session.get("invite_token"):
        existing = RoleProfile.query.filter_by(user_id=user.id, property_id=session["property_id"]).first()
        if existing:
            session["role_profile_id"] = existing.id
            session.pop("invite_token", None)
            return redirect(url_for("dashboard"))
        return redirect(url_for("role_selection"))

    existing = RoleProfile.query.filter_by(user_id=user.id).order_by(RoleProfile.id.desc()).first()
    if existing:
        prop = Property.query.get(existing.property_id)
        session["role_profile_id"] = existing.id
        session["property_id"] = existing.property_id
        session["property_type"] = prop.property_type
        session["sub_room_id"] = existing.sub_room_id
        return redirect(url_for("dashboard"))

    return redirect(url_for("property_setup"))


# ---------------------------------------------------------------------------
# Auth: signup / OTP
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    return redirect(url_for("signup"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    invite_token = request.args.get("invite")
    if invite_token:
        resolved = resolve_invite_token(invite_token)
        if resolved:
            kind, obj = resolved
            session.clear()
            session["invite_token"] = invite_token
            if kind == "property":
                session["property_id"] = obj.id
                session["property_type"] = obj.property_type
                session["sub_room_id"] = None
            else:
                session["property_id"] = obj.property_id
                session["property_type"] = "office"
                session["sub_room_id"] = obj.id
        else:
            flash("This invite link is invalid or has expired.", "danger")

    if request.method == "POST":
        contact_type = request.form.get("contact_type")
        raw_contact = request.form.get("contact", "").strip()
        contact = raw_contact.lower() if contact_type == "email" else raw_contact

        if contact_type not in ("email", "phone"):
            flash("Please choose email or phone.", "danger")
        elif contact_type == "email" and not EMAIL_REGEX.match(contact):
            flash("Please enter a valid email address.", "danger")
        elif contact_type == "phone" and not PHONE_REGEX.match(contact):
            flash("Please enter a valid 10-digit mobile number.", "danger")
        else:
            session["contact"] = contact
            session["contact_type"] = contact_type
            create_and_send_otp(contact)
            return redirect(url_for("verify_otp"))

    invite_info = None
    if session.get("invite_token") and session.get("property_id"):
        prop = Property.query.get(session["property_id"])
        sub_room = SubRoom.query.get(session["sub_room_id"]) if session.get("sub_room_id") else None
        if prop:
            invite_info = {"property": prop, "sub_room": sub_room}

    return render_template("signup.html", invite_info=invite_info)


@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    contact = session.get("contact")
    contact_type = session.get("contact_type")
    if not contact:
        return redirect(url_for("signup"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        otp = (
            OTPRequest.query.filter_by(contact=contact, verified=False)
            .order_by(OTPRequest.id.desc())
            .first()
        )
        if not otp or otp.is_expired():
            flash("Your OTP has expired. Please request a new one.", "danger")
        elif otp.code != code:
            flash("Incorrect OTP. Please try again.", "danger")
        else:
            otp.verified = True
            db.session.commit()
            user = find_or_create_user(contact_type, contact)
            session["user_id"] = user.id
            return route_after_login(user)

    return render_template("verify_otp.html", masked_contact=mask_contact(contact, contact_type))


@app.route("/resend-otp", methods=["POST"])
def resend_otp():
    contact = session.get("contact")
    if not contact:
        return redirect(url_for("signup"))
    create_and_send_otp(contact)
    return redirect(url_for("verify_otp"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("signup"))


@app.route("/join/<token>")
def join(token):
    return redirect(url_for("signup", invite=token))


# ---------------------------------------------------------------------------
# Property creation
# ---------------------------------------------------------------------------


@app.route("/property-setup", methods=["GET", "POST"])
@login_required
def property_setup():
    if request.method == "POST":
        property_type = request.form.get("property_type")
        if property_type not in dict(PROPERTY_TYPES):
            flash("Please select a property type.", "danger")
        else:
            session["property_type"] = property_type
            session.pop("property_id", None)
            session.pop("sub_room_id", None)
            if property_type == "office":
                return redirect(url_for("property_form_office"))
            return redirect(url_for("property_form"))

    return render_template("property_setup.html", property_types=PROPERTY_TYPES)


@app.route("/property-form", methods=["GET", "POST"])
@login_required
def property_form():
    if session.get("property_type") not in RESIDENTIAL_PROPERTY_TYPES:
        return redirect(url_for("property_setup"))

    if request.method == "POST":
        property_type = request.form.get("property_type")
        name = request.form.get("name", "").strip()
        address = request.form.get("address", "").strip()
        num_flats = request.form.get("num_flats", "").strip()
        extra_parking = request.form.get("extra_parking", "0").strip()

        errors = []
        if property_type not in RESIDENTIAL_PROPERTY_TYPES:
            errors.append("Please select Apartment or Gated Community.")
        if not name:
            errors.append("Please enter the property name.")
        if not address:
            errors.append("Please enter the address.")
        if not num_flats.isdigit():
            errors.append("Number of flats must be a number.")
        if extra_parking and not extra_parking.isdigit():
            errors.append("Extra parking spaces must be a number.")

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
            session["property_id"] = prop.id
            session["property_type"] = prop.property_type
            session["sub_room_id"] = None
            return redirect(url_for("invite_links"))

    return render_template(
        "property_form_residential.html",
        property_type=session.get("property_type"),
        form_data=request.form,
    )


@app.route("/property-form/office", methods=["GET", "POST"])
@login_required
def property_form_office():
    if session.get("property_type") != "office":
        return redirect(url_for("property_setup"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        address = request.form.get("address", "").strip()
        company_names = request.form.getlist("company_name[]")
        num_employees_list = request.form.getlist("num_employees[]")
        num_parking_list = request.form.getlist("num_parking_spaces[]")
        floor_alloc_list = request.form.getlist("floor_allocation[]")
        extra_parking_list = request.form.getlist("extra_parking[]")

        errors = []
        if not name:
            errors.append("Please enter the property name.")
        if not address:
            errors.append("Please enter the address.")

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
                errors.append(f"Please enter valid numbers for company '{company_name}'.")
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
            errors.append("Please add at least one company.")

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
                db.session.add(SubRoom(property_id=prop.id, **company))
            db.session.commit()
            session["property_id"] = prop.id
            session["property_type"] = "office"
            session["sub_room_id"] = None
            return redirect(url_for("invite_links"))

    return render_template("property_form_office.html", form_data=request.form)


@app.route("/invite-links")
@login_required
def invite_links():
    property_id = session.get("property_id")
    if not property_id:
        return redirect(url_for("property_setup"))

    prop = Property.query.get_or_404(property_id)
    invite_url = url_for("join", token=prop.invite_token, _external=True)
    sub_room_links = [
        (sub_room, url_for("join", token=sub_room.invite_token, _external=True)) for sub_room in prop.sub_rooms
    ]

    return render_template(
        "invite_links.html",
        property=prop,
        invite_url=invite_url,
        sub_room_links=sub_room_links,
    )


@app.route("/invite-links/next")
@login_required
def invite_links_next():
    if not session.get("property_id"):
        return redirect(url_for("property_setup"))
    return redirect(url_for("role_selection"))


# ---------------------------------------------------------------------------
# Role selection
# ---------------------------------------------------------------------------


@app.route("/role-selection", methods=["GET", "POST"])
@login_required
def role_selection():
    property_id = session.get("property_id")
    if not property_id:
        return redirect(url_for("property_setup"))

    prop = Property.query.get_or_404(property_id)
    roles = RESIDENTIAL_ROLES if prop.property_type in RESIDENTIAL_PROPERTY_TYPES else OFFICE_ROLES

    if request.method == "POST":
        role = request.form.get("role")
        if role not in dict(roles):
            flash("Please select a role.", "danger")
        else:
            session["selected_role"] = role
            return redirect(url_for("role_form", role=role))

    return render_template("role_selection.html", roles=roles, property=prop)


# ---------------------------------------------------------------------------
# Role forms
# ---------------------------------------------------------------------------


def _strip(form, field):
    return form.get(field, "").strip()


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


@app.route("/role-form/<role>", methods=["GET", "POST"])
@login_required
def role_form(role):
    property_id = session.get("property_id")
    if not property_id:
        return redirect(url_for("property_setup"))

    prop = Property.query.get_or_404(property_id)
    sub_room_id = session.get("sub_room_id")
    sub_room = SubRoom.query.get(sub_room_id) if sub_room_id else None

    allowed_roles = dict(RESIDENTIAL_ROLES if prop.property_type in RESIDENTIAL_PROPERTY_TYPES else OFFICE_ROLES)
    if role not in allowed_roles:
        abort(404)

    if request.method == "POST":
        vehicles = []
        bank = None

        if role == "owner":
            data = parse_owner_form(request.form)
            vehicles = parse_vehicle_table(request.form)
            bank = parse_bank_details(request.form, role)
        elif role == "tenant":
            data = parse_tenant_form(request.form)
            vehicles = parse_vehicle_table(request.form)
            bank = parse_bank_details(request.form, role)
        elif role == "committee":
            data = parse_committee_form(request.form)
            vehicles = parse_vehicle_table(request.form)
            bank = parse_bank_details(request.form, role)
        elif role == "security":
            data = parse_security_form(request.form)
        else:  # employee or manager
            data = parse_employee_form(request.form)
            if role == "manager":
                bank = parse_bank_details(request.form, role)

        errors = []
        for field in REQUIRED_FIELDS[role]:
            if not data.get(field):
                errors.append("Please fill in all required fields.")
                break

        if role in ("employee", "manager") and data.get("transport") == "self":
            if not data.get("vehicle_type") or not data.get("vehicle_number"):
                errors.append("Please enter your vehicle type and number for self-transport.")

        if bank is not None:
            for field in REQUIRED_BANK_FIELDS:
                if not bank.get(field):
                    errors.append("Please fill in all required bank details.")
                    break

        if role in ("owner", "tenant", "committee") and not vehicles:
            errors.append("Please add at least one vehicle.")

        if vehicles:
            duplicates = find_duplicate_vehicle_numbers(property_id, [v["vehicle_number"] for v in vehicles])
            if duplicates:
                errors.append(f"Vehicle number(s) already registered to another member: {', '.join(duplicates)}")

        if role in ("employee", "manager") and data.get("transport") == "self":
            duplicates = find_duplicate_vehicle_numbers(property_id, [data["vehicle_number"]])
            if duplicates:
                errors.append(f"Vehicle number {duplicates[0]} is already registered to another member.")

        if role in ("employee", "manager") and is_duplicate_employee_id(
            property_id, sub_room_id, data.get("employee_id")
        ):
            errors.append("This Employee ID is already registered.")

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
            session["role_profile_id"] = role_profile.id
            session.pop("invite_token", None)
            return redirect(url_for("dashboard"))

        for error in errors:
            flash(error, "danger")

    return render_template(
        ROLE_TEMPLATES[role],
        property=prop,
        sub_room=sub_room,
        vehicle_types=VEHICLE_TYPES,
        form_data=request.form,
    )


# ---------------------------------------------------------------------------
# Dashboard & profile (placeholders - full dashboards built in the next phase)
# ---------------------------------------------------------------------------


@app.route("/dashboard")
@login_required
def dashboard():
    role_profile = RoleProfile.query.get(session.get("role_profile_id"))
    if role_profile is None:
        return redirect(url_for("property_setup"))

    prop = Property.query.get(role_profile.property_id)
    sub_room = SubRoom.query.get(role_profile.sub_room_id) if role_profile.sub_room_id else None

    return render_template(
        "dashboard.html",
        role_profile=role_profile,
        property=prop,
        sub_room=sub_room,
        show_sidebar=True,
    )


@app.route("/my-profile", methods=["GET", "POST"])
@login_required
def my_profile():
    role_profile = RoleProfile.query.get(session.get("role_profile_id"))
    if role_profile is None:
        return redirect(url_for("property_setup"))

    prop = Property.query.get(role_profile.property_id)
    sub_room = SubRoom.query.get(role_profile.sub_room_id) if role_profile.sub_room_id else None

    if request.method == "POST":
        data = dict(role_profile.data)

        if role_profile.role in ("employee", "manager", "security"):
            data["shift_from"] = _strip(request.form, "shift_from")
            data["shift_to"] = _strip(request.form, "shift_to")

        if role_profile.role in ("employee", "manager") and data.get("transport") == "self":
            data["vehicle_type"] = _strip(request.form, "vehicle_type")
            data["vehicle_number"] = _strip(request.form, "vehicle_number").upper()

        role_profile.data = data

        if role_profile.role == "manager" and role_profile.bank_detail:
            bank = role_profile.bank_detail
            bank.bank_name = _strip(request.form, "bank_name")
            bank.branch = _strip(request.form, "branch")
            bank.ifsc_code = _strip(request.form, "ifsc_code").upper()
            bank.account_number = _strip(request.form, "account_number")
            bank.expiry_date = _strip(request.form, "expiry_date")
            raw_rent = _strip(request.form, "rent_per_hour")
            if raw_rent:
                bank.rent_per_hour = float(raw_rent)

        db.session.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("my_profile"))

    return render_template(
        "my_profile.html",
        role_profile=role_profile,
        property=prop,
        sub_room=sub_room,
        vehicle_types=VEHICLE_TYPES,
        show_sidebar=True,
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
