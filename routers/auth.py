"""Auth routes: signup / verify-OTP / resend-OTP / logout / join / set-language."""

import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter
from starlette.requests import Request

from constants import OTP_VALIDITY_MINUTES
from database import db
from helpers import EMAIL_REGEX, PHONE_REGEX
from i18n import _
from models import OTPRequest, Property, RoleProfile, SubRoom, User
from templating import render
from webcompat import flash, redirect, session, url_for

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    flash(
        _(
            "Demo mode: your verification code is %(code)s (valid for %(minutes)s minutes).",
            code=code,
            minutes=OTP_VALIDITY_MINUTES,
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
        existing = RoleProfile.query.filter_by(
            user_id=user.id, property_id=session["property_id"]
        ).first()
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
# Routes
# ---------------------------------------------------------------------------


@router.api_route("/", methods=["GET"], name="index")
async def index(request: Request):
    return redirect(url_for("signup"))


@router.api_route("/set-language/{lang_code}", methods=["GET"], name="set_language")
async def set_language(request: Request, lang_code: str):
    from i18n import LANGUAGES

    if lang_code in LANGUAGES:
        session["lang"] = lang_code
    referer = request.headers.get("referer")
    return redirect(referer or url_for("index"))


@router.api_route("/signup", methods=["GET", "POST"], name="signup")
async def signup(request: Request):
    invite_token = request.query_params.get("invite")
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
        form = await request.form()
        contact_type = form.get("contact_type")
        raw_contact = form.get("contact", "").strip()
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

    return render(request, "signup.html", invite_info=invite_info)


@router.api_route("/verify-otp", methods=["GET", "POST"], name="verify_otp")
async def verify_otp(request: Request):
    contact = session.get("contact")
    contact_type = session.get("contact_type")
    if not contact:
        return redirect(url_for("signup"))

    if request.method == "POST":
        form = await request.form()
        code = form.get("code", "").strip()
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

    return render(
        request, "verify_otp.html", masked_contact=mask_contact(contact, contact_type)
    )


@router.api_route("/resend-otp", methods=["POST"], name="resend_otp")
async def resend_otp(request: Request):
    contact = session.get("contact")
    if not contact:
        return redirect(url_for("signup"))
    create_and_send_otp(contact)
    return redirect(url_for("verify_otp"))


@router.api_route("/logout", methods=["GET"], name="logout")
async def logout(request: Request):
    lang = session.get("lang")
    session.clear()
    if lang:
        session["lang"] = lang
    return redirect(url_for("signup"))


@router.api_route("/join/{token}", methods=["GET"], name="join")
async def join(request: Request, token: str):
    return redirect(url_for("signup", invite=token))
