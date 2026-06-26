"""FluxPark AI assistant built on Google's Agent Development Kit (ADK).

Replaces the old single-shot chat-completion call in ai_engine.py with a real
agent: an LlmAgent with instructions and database-backed tools, driven by an
ADK Runner reasoning loop, with conversation memory persisted via
DatabaseSessionService (same SQLite file as the rest of the app).

The configured provider (Ollama / BYOK / Gemini) is wrapped through LiteLlm so
all three keep working with the existing per-role-profile AISettings, while
the agent itself — instructions, tools, reasoning loop — is genuine ADK.
"""

import contextlib
from datetime import datetime as _datetime

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types

from ai_engine import (
    DEFAULT_BYOK_BASE_URL,
    DEFAULT_BYOK_MODEL,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
)
from constants import PROPERTY_TYPE_LABELS, ROLE_LABELS, VEHICLE_TYPES
from database import DATABASE_URL, db
from faq_search import search_faq
from i18n import get_locale

APP_NAME = "fluxpark"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"

_session_service = None  # pylint: disable=invalid-name


def _async_db_url(url: str) -> str:
    """DatabaseSessionService uses SQLAlchemy's async engine, which needs an
    async-capable driver — the rest of the app's sync sqlite:/// URL needs
    the aiosqlite driver spliced in."""
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


def _get_session_service():
    global _session_service  # pylint: disable=global-statement
    if _session_service is None:
        _session_service = DatabaseSessionService(db_url=_async_db_url(DATABASE_URL))
    return _session_service


def _resolve_model(settings):
    """Map an AISettings row onto a LiteLlm model the ADK Agent can call.

    All three providers go through LiteLLM (ADK's documented bridge for
    non-Gemini-native models), so Ollama and BYOK keep working exactly as
    configured today while gaining ADK's tool-calling and session memory.
    """
    provider = settings.provider if settings else "ollama"

    if provider == "gemini" and settings and settings.gemini_api_key:
        model_name = settings.gemini_model or DEFAULT_GEMINI_MODEL
        return LiteLlm(model=f"gemini/{model_name}", api_key=settings.gemini_api_key)

    if provider == "byok" and settings and settings.byok_api_key:
        model_name = settings.byok_model or DEFAULT_BYOK_MODEL
        base_url = settings.byok_base_url or DEFAULT_BYOK_BASE_URL
        return LiteLlm(
            model=f"openai/{model_name}", api_base=base_url, api_key=settings.byok_api_key
        )

    host = (
        settings.ollama_host if settings and settings.ollama_host else DEFAULT_OLLAMA_HOST
    ).rstrip("/")
    model_name = (
        settings.ollama_model if settings and settings.ollama_model else DEFAULT_OLLAMA_MODEL
    )
    return LiteLlm(model=f"ollama_chat/{model_name}", api_base=host)


def _build_instruction(role_profile):
    from models import Property, SubRoom

    prop = Property.query.get(role_profile.property_id)
    role_label = str(ROLE_LABELS.get(role_profile.role, role_profile.role.title()))
    property_label = str(PROPERTY_TYPE_LABELS.get(prop.property_type, prop.property_type))

    lines = [
        "You are the FluxPark AI assistant, an agentic helper built into a smart "
        "parking and access management app for residential and office properties.",
        f'The current user is a {role_label} at "{prop.name}" ({property_label}).',
        "Use your tools to look up real data (parking slots, visitor requests, "
        "payments, notifications) before answering instead of guessing — never "
        "make up slot numbers, statuses, or amounts.",
        "For 'how do I...' or 'what does ... mean' questions about using FluxPark "
        "itself, call search_faq_corpus first and base your answer on its result "
        "if found=true, rather than guessing at how a feature works.",
        "Keep answers short, friendly, and practical.",
    ]
    if role_profile.role in ("owner", "tenant", "committee"):
        lines.append(
            "If the user asks you to log or invite a visitor, use the "
            "submit_visitor_request tool instead of just describing how to do it."
        )
    if role_profile.sub_room_id:
        sub_room = SubRoom.query.get(role_profile.sub_room_id)
        if sub_room:
            lines.append(f'Their company is "{sub_room.company_name}".')
    return "\n".join(lines)


def _build_tools(role_profile):
    """Bind read/write tool functions to this request's role_profile.

    ADK turns plain functions into callable tools using their name, type
    hints, and docstring as the function-calling schema — no extra
    boilerplate needed beyond a closure that captures the current user.
    """

    def get_my_parking_slots() -> list[dict]:
        """Look up the user's own parking slots and their current status."""
        from models import ParkingSlot
        from parking_engine import compute_slot_status, now_ist

        today = now_ist().date()
        now_dt = now_ist()
        if role_profile.role in ("owner", "tenant", "committee"):
            slots = ParkingSlot.query.filter_by(
                property_id=role_profile.property_id, home_role_profile_id=role_profile.id
            ).all()
        else:
            slots = ParkingSlot.query.filter_by(
                property_id=role_profile.property_id, sub_room_id=role_profile.sub_room_id
            ).all()
        return [
            {
                "slot_number": s.slot_number,
                "floor": s.floor or "-",
                "status": compute_slot_status(s, today, now_dt),
            }
            for s in slots
        ]

    def get_today_visitor_requests() -> list[dict]:
        """Look up the visitor requests this user is hosting today, with their status."""
        from models import VisitorRequest
        from parking_engine import now_ist

        today = now_ist().date()
        rows = VisitorRequest.query.filter_by(
            host_role_profile_id=role_profile.id, date=today
        ).all()
        return [
            {
                "visitor_name": r.visitor_name,
                "vehicle_number": r.vehicle_number,
                "from_time": r.from_time.strftime("%H:%M"),
                "to_time": r.to_time.strftime("%H:%M"),
                "status": r.status,
            }
            for r in rows
        ]

    def get_pending_payments() -> list[dict]:
        """Look up the user's pending (unpaid) payments that they owe."""
        from models import Transaction

        rows = Transaction.query.filter_by(
            payer_role_profile_id=role_profile.id, status="pending"
        ).all()
        return [
            {
                "description": t.description,
                "amount": t.total_amount,
                "created_at": t.created_at.isoformat(),
            }
            for t in rows
        ]

    def get_unread_notifications() -> list[dict]:
        """Look up the user's unread notifications."""
        from models import Notification

        rows = Notification.query.filter_by(role_profile_id=role_profile.id, is_read=False).all()
        return [
            {"title": n.title, "body": n.body, "created_at": n.created_at.isoformat()} for n in rows
        ]

    def search_faq_corpus(query: str) -> dict:
        """Search FluxPark's own FAQ corpus for a question close to `query`
        (e.g. "how do I switch rooms", "what does pending mean") and return
        its vetted question/answer. Returns {"found": false} if nothing in
        the corpus is a close enough match -- in that case, answer from your
        own knowledge of the app instead of guessing at FluxPark specifics.
        """
        match = search_faq(query, lang=get_locale())
        if match is None:
            return {"found": False}
        return {"found": True, **match}

    def submit_visitor_request(
        visitor_name: str,
        visitor_phone: str,
        vehicle_type: str,
        vehicle_number: str,
        date: str,
        from_time: str,
        to_time: str,
    ) -> str:
        """Create a new visitor request for this resident.

        Only owners, tenants, and committee heads can use this tool. `date`
        must be in YYYY-MM-DD format, `from_time`/`to_time` in 24-hour HH:MM
        format, and `vehicle_type` one of: Bike, Car, Auto, Truck, Camper,
        Cycle, Other. Returns a confirmation message.
        """
        if role_profile.role not in ("owner", "tenant", "committee"):
            return "Only owners, tenants, and committee heads can submit visitor requests."
        if vehicle_type not in VEHICLE_TYPES:
            return f"Invalid vehicle_type. Must be one of: {', '.join(VEHICLE_TYPES)}."

        from models import VisitorRequest
        from parking_engine import try_match_request

        try:
            parsed_date = _datetime.strptime(date, "%Y-%m-%d").date()
            parsed_from = _datetime.strptime(from_time, "%H:%M").time()
            parsed_to = _datetime.strptime(to_time, "%H:%M").time()
        except ValueError:
            return "Invalid date/time format. Use YYYY-MM-DD for date and HH:MM for times."

        vr = VisitorRequest(
            property_id=role_profile.property_id,
            host_role_profile_id=role_profile.id,
            visitor_name=visitor_name,
            visitor_phone=visitor_phone,
            vehicle_type=vehicle_type,
            vehicle_number=vehicle_number.upper(),
            date=parsed_date,
            from_time=parsed_from,
            to_time=parsed_to,
            status="pending_allocation",
        )
        db.session.add(vr)
        db.session.flush()
        try_match_request(vr)
        db.session.commit()
        if vr.status == "allocated":
            return f"Visitor request created for {visitor_name} and a parking slot was allocated."
        return f"Visitor request created for {visitor_name}. We'll notify you once a slot is available."

    tools = [
        get_my_parking_slots,
        get_today_visitor_requests,
        get_pending_payments,
        get_unread_notifications,
        search_faq_corpus,
    ]
    if role_profile.role in ("owner", "tenant", "committee"):
        tools.append(submit_visitor_request)
    return tools


def build_agent(role_profile, settings):
    return Agent(
        name="fluxpark_assistant",
        model=_resolve_model(settings),
        instruction=_build_instruction(role_profile),
        tools=_build_tools(role_profile),
    )


def _session_identity(role_profile):
    return str(role_profile.user_id), f"role-profile-{role_profile.id}"


async def _ensure_session(role_profile):
    service = _get_session_service()
    user_id, session_id = _session_identity(role_profile)
    existing = await service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    if existing is None:
        await service.create_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    return user_id, session_id


def _friendly_error(exc) -> str:
    text = str(exc)
    lowered = text.lower()
    if "connection" in lowered or "max retries" in lowered or "refused" in lowered:
        return "Could not reach the configured AI provider. Check your AI settings and try again."
    if "api key" in lowered or "unauthorized" in lowered or "401" in text:
        return "The AI provider rejected the request — check your API key in AI Settings."
    return f"AI provider error: {text[:300]}"


async def get_agent_reply(role_profile, settings, user_text):
    """Run one turn of the FluxPark agent. Returns (reply_text, error_message)."""
    try:
        user_id, session_id = await _ensure_session(role_profile)
        agent = build_agent(role_profile, settings)
        runner = Runner(app_name=APP_NAME, agent=agent, session_service=_get_session_service())
        message = types.Content(role="user", parts=[types.Part.from_text(text=user_text)])

        reply_text = None
        async for event in runner.run_async(
            user_id=user_id, session_id=session_id, new_message=message
        ):
            if event.is_final_response() and event.content and event.content.parts:
                reply_text = "".join(part.text for part in event.content.parts if part.text)

        if not reply_text:
            return None, "The AI assistant didn't return a response."
        return reply_text, None
    except Exception as exc:  # noqa: BLE001 - surfaced to the user as a flash message
        return None, _friendly_error(exc)


async def reset_session(role_profile):
    """Drop the agent's persistent memory for this role profile (used by 'Clear conversation')."""
    service = _get_session_service()
    user_id, session_id = _session_identity(role_profile)
    with contextlib.suppress(Exception):  # nothing to clear is not an error
        await service.delete_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
