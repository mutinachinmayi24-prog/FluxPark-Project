"""Jinja2 template rendering: render_template replacement plus the
inject_nav_items context processor (nav_items, unread_notifications,
get_flashed_messages, current_endpoint, LANGUAGES, get_locale, ...).
"""

from starlette.templating import Jinja2Templates

from constants import (
    PROPERTY_TYPE_LABELS,
    RESIDENTIAL_PROPERTY_TYPES,
    ROLE_LABELS,
    VEHICLE_TYPE_LABELS,
)
from i18n import LANGUAGES, _, get_locale, ngettext
from models import Notification, Property, RoleProfile
from parking_engine import (
    REQUEST_STATUS_CLASSES,
    REQUEST_STATUS_LABELS,
    SLOT_STATUS_CLASSES,
    SLOT_STATUS_LABELS,
)
from webcompat import get_flashed_messages, session, url_for

templates = Jinja2Templates(directory="templates")
templates.env.globals.update(
    SLOT_STATUS_LABELS=SLOT_STATUS_LABELS,
    SLOT_STATUS_CLASSES=SLOT_STATUS_CLASSES,
    REQUEST_STATUS_LABELS=REQUEST_STATUS_LABELS,
    REQUEST_STATUS_CLASSES=REQUEST_STATUS_CLASSES,
    ROLE_LABELS=ROLE_LABELS,
    PROPERTY_TYPE_LABELS=PROPERTY_TYPE_LABELS,
    VEHICLE_TYPE_LABELS=VEHICLE_TYPE_LABELS,
    LANGUAGES=LANGUAGES,
    get_locale=get_locale,
    url_for=url_for,
    get_flashed_messages=get_flashed_messages,
    _=_,
    ngettext=ngettext,
)


def build_nav_items(role_profile):
    prop = Property.query.get(role_profile.property_id)
    role = role_profile.role
    items = [{"endpoint": "dashboard", "label": _("Dashboard"), "icon": "bi-speedometer2"}]
    items.append({"endpoint": "ai_assistant", "label": _("AI Assistant"), "icon": "bi-robot"})

    if prop and prop.property_type in RESIDENTIAL_PROPERTY_TYPES:
        if role in ("owner", "tenant", "committee"):
            items.append(
                {"endpoint": "visitor_request", "label": _("Visitor Request"), "icon": "bi-person-plus"}
            )
            items.append(
                {
                    "endpoint": "parking_availability",
                    "label": _("Parking Availability"),
                    "icon": "bi-calendar2-check",
                }
            )

        items.append({"endpoint": "parking_slots", "label": _("Parking Slots"), "icon": "bi-grid-3x3-gap"})
        items.append({"endpoint": "parking_map", "label": _("Parking Map"), "icon": "bi-map"})

        if role == "security":
            items.append(
                {"endpoint": "security_scan", "label": _("Scan Entry / Exit"), "icon": "bi-qr-code-scan"}
            )
            items.append(
                {
                    "endpoint": "unexpected_visitor",
                    "label": _("Unexpected Visitor"),
                    "icon": "bi-person-exclamation",
                }
            )
            items.append({"endpoint": "visitor_log", "label": _("Visitor Log"), "icon": "bi-journal-text"})

        items.append({"endpoint": "notifications", "label": _("Notifications"), "icon": "bi-bell"})

        if role in ("owner", "tenant", "committee"):
            items.append({"endpoint": "payments", "label": _("Payments"), "icon": "bi-cash-coin"})

        if role in ("owner", "committee"):
            items.append({"endpoint": "members", "label": _("Members"), "icon": "bi-people"})
            items.append({"endpoint": "visitor_log", "label": _("Visitor Log"), "icon": "bi-journal-text"})
            items.append(
                {"endpoint": "invite_links", "label": _("Invite Links"), "icon": "bi-person-plus-fill"}
            )
    else:
        if role in ("employee", "manager"):
            items.append(
                {"endpoint": "parking_slots", "label": _("Company Parking"), "icon": "bi-grid-3x3-gap"}
            )
            items.append({"endpoint": "parking_map", "label": _("Parking Map"), "icon": "bi-map"})
            items.append(
                {"endpoint": "transport_request", "label": _("Transport Request"), "icon": "bi-car-front"}
            )

        if role == "security":
            items.append(
                {"endpoint": "security_scan", "label": _("Scan Entry / Exit"), "icon": "bi-qr-code-scan"}
            )
            items.append(
                {
                    "endpoint": "unexpected_visitor",
                    "label": _("Unexpected Visitor"),
                    "icon": "bi-person-exclamation",
                }
            )
            items.append({"endpoint": "visitor_log", "label": _("Visitor Log"), "icon": "bi-journal-text"})

        items.append({"endpoint": "notifications", "label": _("Notifications"), "icon": "bi-bell"})

        if role in ("employee", "manager"):
            items.append({"endpoint": "members", "label": _("Team"), "icon": "bi-people"})

        if role == "manager":
            items.append({"endpoint": "visitor_log", "label": _("Visitor Log"), "icon": "bi-journal-text"})
            items.append({"endpoint": "payments", "label": _("Rent Ledger"), "icon": "bi-cash-coin"})
            items.append(
                {"endpoint": "invite_links", "label": _("Invite Links"), "icon": "bi-person-plus-fill"}
            )

    items.append({"endpoint": "my_rooms", "label": _("My Rooms"), "icon": "bi-door-open"})
    items.append({"endpoint": "my_profile", "label": _("My Profile"), "icon": "bi-person-circle"})
    return items


def render(request, name, status_code=200, **context):
    role_profile_id = session.get("role_profile_id")
    if role_profile_id:
        role_profile = RoleProfile.query.get(role_profile_id)
        if role_profile is not None:
            unread_count = Notification.query.filter_by(
                role_profile_id=role_profile.id, is_read=False
            ).count()
            context.setdefault("nav_items", build_nav_items(role_profile))
            context.setdefault("unread_notifications", unread_count)

    route = request.scope.get("route")
    context.setdefault("current_endpoint", route.name if route else None)
    return templates.TemplateResponse(request, name, context, status_code=status_code)
