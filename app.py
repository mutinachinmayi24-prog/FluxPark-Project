import csv
import io
import os
import re
import secrets
from datetime import datetime, time, timedelta
from functools import wraps

import qrcode
from flask import (
    Flask,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_babel import Babel, _, get_locale

from constants import (
    OFFICE_ROLES,
    OTP_VALIDITY_MINUTES,
    PROPERTY_TYPE_LABELS,
    PROPERTY_TYPES,
    RESIDENTIAL_PROPERTY_TYPES,
    RESIDENTIAL_ROLES,
    ROLE_LABELS,
    VEHICLE_TYPE_LABELS,
    VEHICLE_TYPES,
)
from ai_engine import (
    DEFAULT_BYOK_BASE_URL,
    DEFAULT_BYOK_MODEL,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    get_chat_reply,
    ollama_status,
)
from extensions import db
from models import (
    AIChatMessage,
    AISettings,
    BankDetail,
    Notification,
    OTPRequest,
    ParkingSlot,
    Property,
    RoleProfile,
    SlotAvailability,
    SubRoom,
    Transaction,
    TransportRequest,
    User,
    Vehicle,
    VisitorRequest,
)
from parking_engine import (
    BUFFER_MINUTES,
    REQUEST_STATUS_CLASSES,
    REQUEST_STATUS_LABELS,
    SLOT_STATUS_CLASSES,
    SLOT_STATUS_LABELS,
    allocate_unexpected_visitor,
    compute_slot_status,
    generate_office_parking_slots,
    generate_parking_slots,
    handle_emergency_return,
    link_home_slot,
    notify,
    now_ist,
    run_pending_transport_allocations,
    try_match_availability,
    try_match_request,
)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["LANGUAGES"] = {"en": "English", "hi": "हिन्दी", "te": "తెలుగు"}
app.config["BABEL_DEFAULT_LOCALE"] = "en"
app.config["BABEL_TRANSLATION_DIRECTORIES"] = "translations"

db.init_app(app)

with app.app_context():
    db.create_all()


def select_locale():
    lang = session.get("lang")
    if lang in app.config["LANGUAGES"]:
        return lang
    return request.accept_languages.best_match(app.config["LANGUAGES"].keys())


babel = Babel(app, locale_selector=select_locale)

app.jinja_env.globals.update(
    SLOT_STATUS_LABELS=SLOT_STATUS_LABELS,
    SLOT_STATUS_CLASSES=SLOT_STATUS_CLASSES,
    REQUEST_STATUS_LABELS=REQUEST_STATUS_LABELS,
    REQUEST_STATUS_CLASSES=REQUEST_STATUS_CLASSES,
    ROLE_LABELS=ROLE_LABELS,
    PROPERTY_TYPE_LABELS=PROPERTY_TYPE_LABELS,
    VEHICLE_TYPE_LABELS=VEHICLE_TYPE_LABELS,
    get_locale=get_locale,
    LANGUAGES=app.config["LANGUAGES"],
)

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


def _require_role_profile():
    role_profile = RoleProfile.query.get(session.get("role_profile_id"))
    if role_profile is None:
        return None, redirect(url_for("property_setup"))
    return role_profile, None


def _parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_time(value):
    return datetime.strptime(value, "%H:%M").time()


def _today_transport_allocations(property_id, today):
    """Map parking_slot_id -> allocated/entered TransportRequest for `today`, for office slots."""
    rows = TransportRequest.query.filter(
        TransportRequest.property_id == property_id,
        TransportRequest.date == today,
        TransportRequest.status.in_(("allocated", "entered")),
        TransportRequest.parking_slot_id.isnot(None),
    ).all()
    return {tr.parking_slot_id: tr for tr in rows}


def _today_visitor_allocations(property_id, today):
    """Map parking_slot_id -> allocated/entered VisitorRequest for `today`, for office slots."""
    rows = VisitorRequest.query.filter(
        VisitorRequest.property_id == property_id,
        VisitorRequest.date == today,
        VisitorRequest.status.in_(("allocated", "entered")),
        VisitorRequest.parking_slot_id.isnot(None),
    ).all()
    return {vr.parking_slot_id: vr for vr in rows}


def _role_profile_label(role_profile):
    d = role_profile.data
    name = (
        d.get("name")
        or d.get("tenant_name")
        or d.get("head_name")
        or d.get("employee_name")
        or "Unknown"
    )
    role_label = str(ROLE_LABELS.get(role_profile.role, role_profile.role.title()))
    flat = d.get("flat_no") or d.get("head_flat_no")
    if flat:
        return f"{flat} - {name} ({role_label})"
    return f"{name} ({role_label})"


def _approvable_host_ids(role_profile):
    """RoleProfile ids whose pending visitor requests this profile may approve/deny.

    Residents (owner/tenant/committee) can only act on their own requests. An
    office manager can act on requests for any employee/manager in their
    company (sub_room); an office employee can only act on their own.
    """
    if role_profile.role == "manager" and role_profile.sub_room_id:
        return [
            rp.id
            for rp in RoleProfile.query.filter(
                RoleProfile.property_id == role_profile.property_id,
                RoleProfile.sub_room_id == role_profile.sub_room_id,
                RoleProfile.role.in_(("employee", "manager")),
            ).all()
        ]
    return [role_profile.id]


def build_nav_items(role_profile):
    prop = Property.query.get(role_profile.property_id)
    role = role_profile.role
    items = [{"endpoint": "dashboard", "label": _("Dashboard"), "icon": "bi-speedometer2"}]
    items.append({"endpoint": "ai_assistant", "label": _("AI Assistant"), "icon": "bi-robot"})

    if prop and prop.property_type in RESIDENTIAL_PROPERTY_TYPES:
        if role in ("owner", "tenant", "committee"):
            items.append({"endpoint": "visitor_request", "label": _("Visitor Request"), "icon": "bi-person-plus"})
            items.append({"endpoint": "parking_availability", "label": _("Parking Availability"), "icon": "bi-calendar2-check"})

        items.append({"endpoint": "parking_slots", "label": _("Parking Slots"), "icon": "bi-grid-3x3-gap"})
        items.append({"endpoint": "parking_map", "label": _("Parking Map"), "icon": "bi-map"})

        if role == "security":
            items.append({"endpoint": "security_scan", "label": _("Scan Entry / Exit"), "icon": "bi-qr-code-scan"})
            items.append({"endpoint": "unexpected_visitor", "label": _("Unexpected Visitor"), "icon": "bi-person-exclamation"})
            items.append({"endpoint": "visitor_log", "label": _("Visitor Log"), "icon": "bi-journal-text"})

        items.append({"endpoint": "notifications", "label": _("Notifications"), "icon": "bi-bell"})

        if role in ("owner", "tenant", "committee"):
            items.append({"endpoint": "payments", "label": _("Payments"), "icon": "bi-cash-coin"})

        if role in ("owner", "committee"):
            items.append({"endpoint": "members", "label": _("Members"), "icon": "bi-people"})
            items.append({"endpoint": "visitor_log", "label": _("Visitor Log"), "icon": "bi-journal-text"})
            items.append({"endpoint": "invite_links", "label": _("Invite Links"), "icon": "bi-person-plus-fill"})
    else:
        if role in ("employee", "manager"):
            items.append({"endpoint": "parking_slots", "label": _("Company Parking"), "icon": "bi-grid-3x3-gap"})
            items.append({"endpoint": "parking_map", "label": _("Parking Map"), "icon": "bi-map"})
            items.append({"endpoint": "transport_request", "label": _("Transport Request"), "icon": "bi-car-front"})

        if role == "security":
            items.append({"endpoint": "security_scan", "label": _("Scan Entry / Exit"), "icon": "bi-qr-code-scan"})
            items.append({"endpoint": "unexpected_visitor", "label": _("Unexpected Visitor"), "icon": "bi-person-exclamation"})
            items.append({"endpoint": "visitor_log", "label": _("Visitor Log"), "icon": "bi-journal-text"})

        items.append({"endpoint": "notifications", "label": _("Notifications"), "icon": "bi-bell"})

        if role in ("employee", "manager"):
            items.append({"endpoint": "members", "label": _("Team"), "icon": "bi-people"})

        if role == "manager":
            items.append({"endpoint": "visitor_log", "label": _("Visitor Log"), "icon": "bi-journal-text"})
            items.append({"endpoint": "payments", "label": _("Rent Ledger"), "icon": "bi-cash-coin"})
            items.append({"endpoint": "invite_links", "label": _("Invite Links"), "icon": "bi-person-plus-fill"})

    items.append({"endpoint": "my_rooms", "label": _("My Rooms"), "icon": "bi-door-open"})
    items.append({"endpoint": "my_profile", "label": _("My Profile"), "icon": "bi-person-circle"})
    return items


@app.context_processor
def inject_nav_items():
    role_profile_id = session.get("role_profile_id")
    if not role_profile_id:
        return {}
    role_profile = RoleProfile.query.get(role_profile_id)
    if role_profile is None:
        return {}
    unread_count = Notification.query.filter_by(role_profile_id=role_profile.id, is_read=False).count()
    return {"nav_items": build_nav_items(role_profile), "unread_notifications": unread_count}


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
        _(
            "Demo mode: your verification code is %(code)s (valid for %(minutes)s minutes).",
            code=code, minutes=OTP_VALIDITY_MINUTES,
        ),
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


@app.route("/set-language/<lang_code>")
def set_language(lang_code):
    if lang_code in app.config["LANGUAGES"]:
        session["lang"] = lang_code
    return redirect(request.referrer or url_for("index"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    invite_token = request.args.get("invite")
    if invite_token:
        resolved = resolve_invite_token(invite_token)
        if resolved:
            kind, obj = resolved
            lang = session.get("lang")
            session.clear()
            if lang:
                session["lang"] = lang
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
            flash(_("This invite link is invalid or has expired."), "danger")

    if request.method == "POST":
        contact_type = request.form.get("contact_type")
        raw_contact = request.form.get("contact", "").strip()
        contact = raw_contact.lower() if contact_type == "email" else raw_contact

        if contact_type not in ("email", "phone"):
            flash(_("Please choose email or phone."), "danger")
        elif contact_type == "email" and not EMAIL_REGEX.match(contact):
            flash(_("Please enter a valid email address."), "danger")
        elif contact_type == "phone" and not PHONE_REGEX.match(contact):
            flash(_("Please enter a valid 10-digit mobile number."), "danger")
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
            flash(_("Your OTP has expired. Please request a new one."), "danger")
        elif otp.code != code:
            flash(_("Incorrect OTP. Please try again."), "danger")
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
    lang = session.get("lang")
    session.clear()
    if lang:
        session["lang"] = lang
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
            flash(_("Please select a property type."), "danger")
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
    onboarding = (
        RoleProfile.query.filter_by(user_id=session["user_id"], property_id=property_id).first()
        is None
    )

    return render_template(
        "invite_links.html",
        property=prop,
        invite_url=invite_url,
        sub_room_links=sub_room_links,
        sub_rooms=prop.sub_rooms,
        onboarding=onboarding,
        show_sidebar=not onboarding,
    )


@app.route("/invite-links/next", methods=["GET", "POST"])
@login_required
def invite_links_next():
    property_id = session.get("property_id")
    if not property_id:
        return redirect(url_for("property_setup"))

    prop = Property.query.get_or_404(property_id)
    if prop.property_type == "office":
        sub_room_id = request.form.get("sub_room_id", type=int)
        valid_ids = {sub_room.id for sub_room in prop.sub_rooms}
        if sub_room_id not in valid_ids:
            flash(_("Please select your company to continue."), "danger")
            return redirect(url_for("invite_links"))
        session["sub_room_id"] = sub_room_id

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
    sub_room = SubRoom.query.get(session["sub_room_id"]) if session.get("sub_room_id") else None

    if request.method == "POST":
        role = request.form.get("role")
        if role not in dict(roles):
            flash(_("Please select a role."), "danger")
        else:
            session["selected_role"] = role
            return redirect(url_for("role_form", role=role))

    return render_template("role_selection.html", roles=roles, property=prop, sub_room=sub_room)


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
                errors.append(_("Vehicle number(s) already registered to another member: %(numbers)s", numbers=', '.join(duplicates)))

        if role in ("employee", "manager") and data.get("transport") == "self":
            duplicates = find_duplicate_vehicle_numbers(property_id, [data["vehicle_number"]])
            if duplicates:
                errors.append(_("Vehicle number %(number)s is already registered to another member.", number=duplicates[0]))

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
        company_slot_rows = [(slot, compute_slot_status(slot, today, now_dt)) for slot in company_slots]
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

    return render_template(
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
        flash(_("Profile updated successfully."), "success")
        return redirect(url_for("my_profile"))

    return render_template(
        "my_profile.html",
        role_profile=role_profile,
        property=prop,
        sub_room=sub_room,
        vehicle_types=VEHICLE_TYPES,
        show_sidebar=True,
    )


# ---------------------------------------------------------------------------
# My Rooms (a user can belong to more than one property/company)
# ---------------------------------------------------------------------------


@app.route("/rooms")
@login_required
def my_rooms():
    role_profiles = (
        RoleProfile.query.filter_by(user_id=session["user_id"])
        .order_by(RoleProfile.id)
        .all()
    )
    return render_template(
        "my_rooms.html",
        role_profiles=role_profiles,
        active_id=session.get("role_profile_id"),
        show_sidebar=True,
    )


@app.route("/rooms/switch/<int:role_profile_id>", methods=["POST"])
@login_required
def switch_room(role_profile_id):
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


@app.route("/rooms/join", methods=["POST"])
@login_required
def join_room():
    raw = request.form.get("invite", "").strip()
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


# ---------------------------------------------------------------------------
# Visitor requests & parking availability (residents)
# ---------------------------------------------------------------------------


@app.route("/visitor-request", methods=["GET", "POST"])
@login_required
def visitor_request():
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role not in ("owner", "tenant", "committee"):
        abort(403)

    if request.method == "POST":
        visitor_name = _strip(request.form, "visitor_name")
        visitor_phone = _strip(request.form, "visitor_phone")
        vehicle_type = _strip(request.form, "vehicle_type")
        vehicle_number = _strip(request.form, "vehicle_number").upper()
        date_str = _strip(request.form, "date")
        from_str = _strip(request.form, "from_time")
        to_str = _strip(request.form, "to_time")

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
                flash(_("Visitor request created. We'll notify you once a slot is available."), "info")
            return redirect(url_for("visitor_request"))

        for error in errors:
            flash(error, "danger")

    requests_ = (
        VisitorRequest.query.filter_by(host_role_profile_id=role_profile.id)
        .order_by(VisitorRequest.date.desc(), VisitorRequest.from_time.desc())
        .all()
    )

    return render_template(
        "visitor_request.html",
        role_profile=role_profile,
        requests=requests_,
        vehicle_types=VEHICLE_TYPES,
        form_data=request.form,
        show_sidebar=True,
    )


@app.route("/parking-availability", methods=["GET", "POST"])
@login_required
def parking_availability():
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

    if request.method == "POST":
        slot_id = _strip(request.form, "parking_slot_id")
        date_str = _strip(request.form, "date")
        from_str = _strip(request.form, "from_time")
        to_str = _strip(request.form, "to_time")
        rent_str = _strip(request.form, "rent_per_hour")

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
        except ValueError:
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

    return render_template(
        "parking_availability.html",
        role_profile=role_profile,
        my_slots=my_slots,
        availabilities=availabilities,
        form_data=request.form,
        show_sidebar=True,
    )


@app.route("/parking-availability/<int:availability_id>/return", methods=["POST"])
@login_required
def parking_availability_return(availability_id):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    availability = SlotAvailability.query.get_or_404(availability_id)
    if availability.role_profile_id != role_profile.id:
        abort(403)
    if availability.status != "matched":
        flash(_("This slot isn't currently matched with a visitor."), "warning")
        return redirect(url_for("parking_availability"))

    handle_emergency_return(availability, now_ist())
    flash(_("Marked as returned. We've notified everyone affected."), "success")
    return redirect(url_for("parking_availability"))


# ---------------------------------------------------------------------------
# Transport requests (office employees & managers)
# ---------------------------------------------------------------------------

TRANSPORT_REQUEST_CUTOFF = time(21, 0)


@app.route("/transport-request", methods=["GET", "POST"])
@login_required
def transport_request():
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role not in ("employee", "manager"):
        abort(403)

    now_dt = now_ist()
    tomorrow = now_dt.date() + timedelta(days=1)
    cutoff_passed = now_dt.time() >= TRANSPORT_REQUEST_CUTOFF

    run_pending_transport_allocations(role_profile.property_id, now_dt)

    existing = TransportRequest.query.filter_by(role_profile_id=role_profile.id, date=tomorrow).first()

    if request.method == "POST":
        action = _strip(request.form, "action")

        if action == "cancel":
            if not existing or existing.status != "pending_allocation":
                flash(_("There's no pending request for tomorrow to cancel."), "warning")
            elif cutoff_passed:
                flash(_("The 9 PM cutoff has passed; this request can no longer be changed."), "danger")
            else:
                db.session.delete(existing)
                db.session.commit()
                flash(_("Transport request for tomorrow cancelled."), "info")
            return redirect(url_for("transport_request"))

        if existing:
            flash(_("You've already submitted a transport request for tomorrow."), "warning")
            return redirect(url_for("transport_request"))
        if cutoff_passed:
            flash(_("Requests for tomorrow's parking must be submitted before 9 PM today."), "danger")
            return redirect(url_for("transport_request"))

        vehicle_type = _strip(request.form, "vehicle_type")
        vehicle_number = _strip(request.form, "vehicle_number").upper()
        from_str = _strip(request.form, "from_time")
        to_str = _strip(request.form, "to_time")

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
            flash(_("Transport request for tomorrow submitted. Slots are allocated after the 9 PM cutoff."), "success")
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

    return render_template(
        "transport_request.html",
        role_profile=role_profile,
        tomorrow=tomorrow,
        existing=existing,
        cutoff_passed=cutoff_passed,
        history=history,
        vehicle_types=VEHICLE_TYPES,
        defaults=defaults,
        show_sidebar=True,
    )


# ---------------------------------------------------------------------------
# Parking slots & map
# ---------------------------------------------------------------------------


@app.route("/parking-slots", methods=["GET", "POST"])
@login_required
def parking_slots():
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    prop = Property.query.get(role_profile.property_id)
    is_office = prop.property_type not in RESIDENTIAL_PROPERTY_TYPES
    can_edit = role_profile.role in ("owner", "committee", "manager")

    if request.method == "POST":
        if not can_edit:
            abort(403)

        slot_ids = request.form.getlist("slot_id[]")
        slot_numbers = request.form.getlist("slot_number[]")
        floors = request.form.getlist("floor[]")
        entrance_ranks = request.form.getlist("entrance_rank[]")
        ramp_ranks = request.form.getlist("ramp_rank[]")
        home_ids = request.form.getlist("home_role_profile_id[]")

        seen_numbers = set()
        errors = []
        rows = []
        for i, raw_number in enumerate(slot_numbers):
            slot_number = raw_number.strip()
            if not slot_number:
                continue
            if slot_number in seen_numbers:
                errors.append(_("Duplicate slot number '%(slot_number)s' in the table.", slot_number=slot_number))
                continue
            seen_numbers.add(slot_number)

            try:
                entrance_rank = int(entrance_ranks[i]) if entrance_ranks[i].strip() else 0
                ramp_rank = int(ramp_ranks[i]) if ramp_ranks[i].strip() else 0
            except ValueError:
                errors.append(_("Entrance/ramp rank for slot '%(slot_number)s' must be a number.", slot_number=slot_number))
                continue

            home_id = home_ids[i].strip()
            rows.append(
                {
                    "slot_id": slot_ids[i].strip(),
                    "slot_number": slot_number,
                    "floor": floors[i].strip() or None,
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
                        errors.append(_("Slot number '%(slot_number)s' is already in use.", slot_number=row["slot_number"]))
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
                        errors.append(_("Slot number '%(slot_number)s' is already in use.", slot_number=row["slot_number"]))
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
    today_visitor_allocations = _today_visitor_allocations(role_profile.property_id, today)

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

    return render_template(
        "parking_slots.html",
        role_profile=role_profile,
        property=prop,
        slot_rows=slot_rows,
        today_allocations=today_allocations,
        today_visitor_allocations=today_visitor_allocations,
        residents=residents,
        can_edit=can_edit,
        role_profile_label=_role_profile_label,
        show_sidebar=True,
    )


@app.route("/parking-map")
@login_required
def parking_map():
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

    return render_template(
        "parking_map.html",
        role_profile=role_profile,
        property=prop,
        floors=floors,
        show_sidebar=True,
    )


# ---------------------------------------------------------------------------
# Notifications & visitor approvals
# ---------------------------------------------------------------------------


@app.route("/notifications")
@login_required
def notifications():
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

    return render_template(
        "notifications.html",
        role_profile=role_profile,
        notifications=items,
        pending_requests=pending_requests,
        role_profile_label=_role_profile_label,
        show_sidebar=True,
    )


@app.route("/notifications/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_notification_read(notification_id):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    notification = Notification.query.get_or_404(notification_id)
    if notification.role_profile_id != role_profile.id:
        abort(403)
    notification.is_read = True
    db.session.commit()
    return redirect(url_for("notifications"))


@app.route("/notifications/mark-all-read", methods=["POST"])
@login_required
def mark_all_notifications_read():
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    Notification.query.filter_by(role_profile_id=role_profile.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return redirect(url_for("notifications"))


@app.route("/visitor-requests/<int:request_id>/approve", methods=["POST"])
@login_required
def approve_visitor_request(request_id):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    vr = VisitorRequest.query.get_or_404(request_id)
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


@app.route("/visitor-requests/<int:request_id>/deny", methods=["POST"])
@login_required
def deny_visitor_request(request_id):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    vr = VisitorRequest.query.get_or_404(request_id)
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


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


@app.route("/payments")
@login_required
def payments():
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role not in ("owner", "tenant", "committee", "manager"):
        abort(403)

    prop = Property.query.get(role_profile.property_id)
    is_office = prop.property_type not in RESIDENTIAL_PROPERTY_TYPES

    payable = (
        Transaction.query.filter_by(payer_role_profile_id=role_profile.id)
        .filter(Transaction.status != "cancelled")
        .order_by(Transaction.created_at.desc())
        .all()
    )
    receivable = (
        Transaction.query.filter_by(payee_role_profile_id=role_profile.id)
        .filter(Transaction.status != "cancelled")
        .order_by(Transaction.created_at.desc())
        .all()
    )

    commission_total = None
    if role_profile.role == "committee":
        commission_total = (
            db.session.query(db.func.sum(Transaction.commission_amount))
            .filter(
                Transaction.property_id == role_profile.property_id,
                Transaction.status != "cancelled",
            )
            .scalar()
            or 0
        )

    return render_template(
        "payments.html",
        role_profile=role_profile,
        property=prop,
        is_office=is_office,
        payable=payable,
        receivable=receivable,
        commission_total=commission_total,
        role_profile_label=_role_profile_label,
        show_sidebar=True,
    )


@app.route("/payments/<int:transaction_id>/mark-paid", methods=["POST"])
@login_required
def mark_payment_paid(transaction_id):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    txn = Transaction.query.get_or_404(transaction_id)
    if txn.payer_role_profile_id != role_profile.id:
        abort(403)
    if txn.status != "pending":
        flash(_("This payment has already been processed."), "warning")
        return redirect(url_for("payments"))

    txn.status = "paid"
    notify(
        txn.payee_role_profile_id,
        "Payment received",
        f"{_role_profile_label(role_profile)} marked a payment of ₹{txn.total_amount} as paid "
        f"for {txn.description}.",
    )
    db.session.commit()
    flash(_("Marked as paid."), "success")
    return redirect(url_for("payments"))


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


@app.route("/members")
@login_required
def members():
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    prop = Property.query.get(role_profile.property_id)
    is_office = prop.property_type not in RESIDENTIAL_PROPERTY_TYPES

    profile_query = RoleProfile.query.filter_by(property_id=role_profile.property_id)
    if is_office:
        profile_query = profile_query.filter_by(sub_room_id=role_profile.sub_room_id)
    profiles = profile_query.order_by(RoleProfile.role, RoleProfile.id).all()

    return render_template(
        "members.html",
        role_profile=role_profile,
        property=prop,
        profiles=profiles,
        can_remove=role_profile.role in ("owner", "committee", "manager"),
        show_sidebar=True,
    )


@app.route("/members/<int:member_id>/remove", methods=["POST"])
@login_required
def remove_member(member_id):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role not in ("owner", "committee", "manager"):
        abort(403)

    member = RoleProfile.query.get_or_404(member_id)
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


def _visitor_log_query(role_profile, prop):
    """Base VisitorRequest query for this property, scoped to the viewer's company for offices."""
    query = VisitorRequest.query.filter_by(property_id=role_profile.property_id)
    is_office = prop.property_type not in RESIDENTIAL_PROPERTY_TYPES
    if is_office and role_profile.sub_room_id:
        host_ids = [
            rp.id
            for rp in RoleProfile.query.filter_by(
                property_id=role_profile.property_id, sub_room_id=role_profile.sub_room_id
            ).all()
        ]
        query = query.filter(VisitorRequest.host_role_profile_id.in_(host_ids))
    return query


@app.route("/visitor-log")
@login_required
def visitor_log():
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role not in ("owner", "committee", "manager", "security"):
        abort(403)

    prop = Property.query.get(role_profile.property_id)
    query = _visitor_log_query(role_profile, prop)

    search = request.args.get("q", "").strip()
    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(
                VisitorRequest.visitor_name.ilike(like),
                VisitorRequest.vehicle_number.ilike(like),
                VisitorRequest.visitor_phone.ilike(like),
            )
        )

    status_filter = request.args.get("status", "").strip()
    if status_filter:
        query = query.filter(VisitorRequest.status == status_filter)

    records = query.order_by(VisitorRequest.date.desc(), VisitorRequest.from_time.desc()).limit(500).all()

    return render_template(
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


@app.route("/visitor-log/export.csv")
@login_required
def export_visitor_log_csv():
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
    writer.writerow([
        "Date", "Visitor Name", "Phone", "Vehicle Type", "Vehicle Number",
        "From", "To", "Purpose", "Host", "Status", "Entry Time", "Exit Time",
    ])
    for r in records:
        writer.writerow([
            r.date.isoformat(),
            r.visitor_name,
            r.visitor_phone,
            r.vehicle_type,
            r.vehicle_number,
            r.from_time.strftime("%H:%M"),
            r.to_time.strftime("%H:%M"),
            r.purpose or "-",
            _role_profile_label(r.host_role_profile),
            REQUEST_STATUS_LABELS.get(r.status, r.status),
            r.entry_time.strftime("%Y-%m-%d %H:%M") if r.entry_time else "-",
            r.exit_time.strftime("%Y-%m-%d %H:%M") if r.exit_time else "-",
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=visitor_log.csv"},
    )


@app.route("/members/export.csv")
@login_required
def export_members_csv():
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
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=members.csv"},
    )


# ---------------------------------------------------------------------------
# AI assistant (local Ollama inference, with BYOK option)
# ---------------------------------------------------------------------------


def _get_ai_settings(role_profile):
    return AISettings.query.filter_by(role_profile_id=role_profile.id).first()


def _ai_system_prompt(role_profile):
    prop = Property.query.get(role_profile.property_id)
    role_label = str(ROLE_LABELS.get(role_profile.role, role_profile.role.title()))
    property_label = str(PROPERTY_TYPE_LABELS.get(prop.property_type, prop.property_type))
    lines = [
        "You are the FluxPark AI assistant, built into a smart parking and access "
        "management app for residential and office properties.",
        f'The current user is a {role_label} at "{prop.name}" ({property_label}).',
        "Help them with questions about parking slots, visitor passes, transport "
        "requests, payments, and how to use FluxPark. Keep answers short, friendly, "
        "and practical.",
    ]
    if role_profile.sub_room_id:
        sub_room = SubRoom.query.get(role_profile.sub_room_id)
        if sub_room:
            lines.append(f'Their company is "{sub_room.company_name}".')
    return "\n".join(lines)


@app.route("/ai-assistant", methods=["GET", "POST"])
@login_required
def ai_assistant():
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    if request.method == "POST":
        if request.form.get("action") == "clear":
            AIChatMessage.query.filter_by(role_profile_id=role_profile.id).delete()
            db.session.commit()
            return redirect(url_for("ai_assistant"))

        user_text = request.form.get("message", "").strip()
        if user_text:
            db.session.add(AIChatMessage(role_profile_id=role_profile.id, role="user", content=user_text))
            db.session.commit()

            history = (
                AIChatMessage.query.filter_by(role_profile_id=role_profile.id)
                .order_by(AIChatMessage.id.desc())
                .limit(20)
                .all()
            )
            history.reverse()
            chat_messages = [{"role": "system", "content": _ai_system_prompt(role_profile)}]
            chat_messages += [{"role": m.role, "content": m.content} for m in history]

            settings = _get_ai_settings(role_profile)
            reply, error = get_chat_reply(settings, chat_messages)
            if error:
                flash(error, "warning")
                reply = reply or _(
                    "Sorry, I couldn't reach the AI provider. Check your AI settings and try again."
                )
            db.session.add(AIChatMessage(role_profile_id=role_profile.id, role="assistant", content=reply))
            db.session.commit()
        return redirect(url_for("ai_assistant"))

    chat_messages = (
        AIChatMessage.query.filter_by(role_profile_id=role_profile.id)
        .order_by(AIChatMessage.id.asc())
        .all()
    )
    settings = _get_ai_settings(role_profile)
    provider = settings.provider if settings else "ollama"
    ollama_host = settings.ollama_host if settings and settings.ollama_host else DEFAULT_OLLAMA_HOST
    is_running, _models, ollama_error = ollama_status(ollama_host)

    return render_template(
        "ai_assistant.html",
        role_profile=role_profile,
        chat_messages=chat_messages,
        provider=provider,
        ollama_running=is_running,
        ollama_error=ollama_error,
        show_sidebar=True,
    )


@app.route("/ai-settings", methods=["GET", "POST"])
@login_required
def ai_settings():
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    settings = _get_ai_settings(role_profile)

    if request.method == "POST":
        action = request.form.get("action", "save")
        if settings is None:
            settings = AISettings(role_profile_id=role_profile.id)
            db.session.add(settings)

        settings.provider = request.form.get("provider", "ollama")
        settings.ollama_host = request.form.get("ollama_host", "").strip() or DEFAULT_OLLAMA_HOST
        settings.ollama_model = request.form.get("ollama_model", "").strip() or DEFAULT_OLLAMA_MODEL
        settings.byok_base_url = request.form.get("byok_base_url", "").strip() or DEFAULT_BYOK_BASE_URL
        settings.byok_model = request.form.get("byok_model", "").strip() or DEFAULT_BYOK_MODEL

        new_key = request.form.get("byok_api_key", "").strip()
        if new_key:
            settings.byok_api_key = new_key
        elif request.form.get("clear_byok_key") == "1":
            settings.byok_api_key = None

        db.session.commit()

        if action == "test":
            is_running, models, error = ollama_status(settings.ollama_host)
            if is_running:
                flash(
                    _("Connected to Ollama at %(host)s. Installed models: %(models)s",
                      host=settings.ollama_host, models=", ".join(models) or _("none")),
                    "success",
                )
            else:
                flash(
                    _("Could not reach Ollama at %(host)s: %(error)s", host=settings.ollama_host, error=error),
                    "danger",
                )
        else:
            flash(_("AI settings saved."), "success")

        return redirect(url_for("ai_settings"))

    provider = settings.provider if settings else "ollama"
    ollama_host = settings.ollama_host if settings and settings.ollama_host else DEFAULT_OLLAMA_HOST
    ollama_model = settings.ollama_model if settings and settings.ollama_model else DEFAULT_OLLAMA_MODEL
    byok_base_url = settings.byok_base_url if settings and settings.byok_base_url else DEFAULT_BYOK_BASE_URL
    byok_model = settings.byok_model if settings and settings.byok_model else DEFAULT_BYOK_MODEL
    has_byok_key = bool(settings and settings.byok_api_key)

    is_running, available_models, ollama_error = ollama_status(ollama_host)

    return render_template(
        "ai_settings.html",
        role_profile=role_profile,
        provider=provider,
        ollama_host=ollama_host,
        ollama_model=ollama_model,
        byok_base_url=byok_base_url,
        byok_model=byok_model,
        has_byok_key=has_byok_key,
        ollama_running=is_running,
        available_models=available_models,
        ollama_error=ollama_error,
        show_sidebar=True,
    )


# ---------------------------------------------------------------------------
# Public visitor pass & QR code
# ---------------------------------------------------------------------------


@app.route("/visitor-pass/<token>")
def visitor_pass(token):
    vr = VisitorRequest.query.filter_by(qr_token=token).first_or_404()
    slot = vr.slot_availability.parking_slot if vr.slot_availability else vr.parking_slot

    return render_template(
        "visitor_pass.html",
        visitor_request=vr,
        slot=slot,
    )


@app.route("/qr/<token>.png")
def qr_image(token):
    vr = VisitorRequest.query.filter_by(qr_token=token).first_or_404()
    pass_url = url_for("visitor_pass", token=vr.qr_token, _external=True)

    img = qrcode.make(pass_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


# ---------------------------------------------------------------------------
# Transport pass & QR code (office)
# ---------------------------------------------------------------------------


@app.route("/transport-pass/<token>")
def transport_pass(token):
    tr = TransportRequest.query.filter_by(qr_token=token).first_or_404()

    return render_template(
        "transport_pass.html",
        transport_request=tr,
    )


@app.route("/transport-qr/<token>.png")
def transport_qr_image(token):
    tr = TransportRequest.query.filter_by(qr_token=token).first_or_404()
    pass_url = url_for("transport_pass", token=tr.qr_token, _external=True)

    img = qrcode.make(pass_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


# ---------------------------------------------------------------------------
# Security: QR scan, entry/exit, unexpected visitors
# ---------------------------------------------------------------------------


@app.route("/security/scan", methods=["GET", "POST"])
@login_required
def security_scan():
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role != "security":
        abort(403)

    if request.method == "POST":
        token = _strip(request.form, "token").rstrip("/").rsplit("/", 1)[-1]
        if VisitorRequest.query.filter_by(qr_token=token, property_id=role_profile.property_id).first():
            return redirect(url_for("security_visitor", token=token))
        if TransportRequest.query.filter_by(qr_token=token, property_id=role_profile.property_id).first():
            return redirect(url_for("security_transport", token=token))
        flash(_("No pass found for that code."), "danger")
        return redirect(url_for("security_scan"))

    return render_template("security_scan.html", role_profile=role_profile, show_sidebar=True)


@app.route("/security/visitor/<token>")
@login_required
def security_visitor(token):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role != "security":
        abort(403)

    vr = VisitorRequest.query.filter_by(qr_token=token, property_id=role_profile.property_id).first_or_404()
    slot = vr.slot_availability.parking_slot if vr.slot_availability else vr.parking_slot

    return render_template(
        "security_visitor.html",
        role_profile=role_profile,
        visitor_request=vr,
        slot=slot,
        role_profile_label=_role_profile_label,
        show_sidebar=True,
    )


@app.route("/security/visitor/<token>/entry", methods=["POST"])
@login_required
def security_visitor_entry(token):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role != "security":
        abort(403)

    vr = VisitorRequest.query.filter_by(qr_token=token, property_id=role_profile.property_id).first_or_404()
    if vr.status != "allocated":
        flash(_("This visitor cannot be marked as entered right now."), "warning")
        return redirect(url_for("security_visitor", token=token))

    vr.status = "entered"
    vr.entry_time = now_ist()
    db.session.commit()
    flash(_("%(name)s marked as entered.", name=vr.visitor_name), "success")
    return redirect(url_for("security_visitor", token=token))


@app.route("/security/visitor/<token>/exit", methods=["POST"])
@login_required
def security_visitor_exit(token):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role != "security":
        abort(403)

    vr = VisitorRequest.query.filter_by(qr_token=token, property_id=role_profile.property_id).first_or_404()
    if vr.status != "entered":
        flash(_("This visitor cannot be marked as exited right now."), "warning")
        return redirect(url_for("security_visitor", token=token))

    vr.status = "exited"
    vr.exit_time = now_ist()
    db.session.commit()
    flash(_("%(name)s marked as exited.", name=vr.visitor_name), "success")
    return redirect(url_for("security_visitor", token=token))


@app.route("/security/transport/<token>")
@login_required
def security_transport(token):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role != "security":
        abort(403)

    tr = TransportRequest.query.filter_by(qr_token=token, property_id=role_profile.property_id).first_or_404()

    return render_template(
        "security_transport.html",
        role_profile=role_profile,
        transport_request=tr,
        show_sidebar=True,
    )


@app.route("/security/transport/<token>/entry", methods=["POST"])
@login_required
def security_transport_entry(token):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role != "security":
        abort(403)

    tr = TransportRequest.query.filter_by(qr_token=token, property_id=role_profile.property_id).first_or_404()
    if tr.status != "allocated":
        flash(_("This pass cannot be marked as entered right now."), "warning")
        return redirect(url_for("security_transport", token=token))

    tr.status = "entered"
    tr.entry_time = now_ist()
    db.session.commit()
    flash(_("Marked as entered."), "success")
    return redirect(url_for("security_transport", token=token))


@app.route("/security/transport/<token>/exit", methods=["POST"])
@login_required
def security_transport_exit(token):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role != "security":
        abort(403)

    tr = TransportRequest.query.filter_by(qr_token=token, property_id=role_profile.property_id).first_or_404()
    if tr.status != "entered":
        flash(_("This pass cannot be marked as exited right now."), "warning")
        return redirect(url_for("security_transport", token=token))

    tr.status = "exited"
    tr.exit_time = now_ist()
    db.session.commit()
    flash(_("Marked as exited."), "success")
    return redirect(url_for("security_transport", token=token))


@app.route("/security/unexpected-visitor", methods=["GET", "POST"])
@login_required
def unexpected_visitor():
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

    if request.method == "POST":
        visitor_name = _strip(request.form, "visitor_name")
        visitor_phone = _strip(request.form, "visitor_phone")
        vehicle_type = _strip(request.form, "vehicle_type")
        vehicle_number = _strip(request.form, "vehicle_number").upper()
        purpose = _strip(request.form, "purpose")
        date_str = _strip(request.form, "date")
        host_id = _strip(request.form, "host_role_profile_id")
        more_than_1hr = request.form.get("more_than_1hr") == "on"

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
        if (
            not host
            or host.property_id != role_profile.property_id
            or host.role not in host_roles
        ):
            errors.append(_("Please select who the visitor is here to see."))

        date_val = _parse_date(date_str) if date_str else None
        from_time = to_time = None

        if more_than_1hr:
            from_str = _strip(request.form, "from_time")
            to_str = _strip(request.form, "to_time")
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

    return render_template(
        "unexpected_visitor.html",
        role_profile=role_profile,
        hosts=hosts,
        recent=recent,
        vehicle_types=VEHICLE_TYPES,
        form_data=request.form,
        role_profile_label=_role_profile_label,
        today=now_ist().date().isoformat(),
        show_sidebar=True,
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
