"""AI assistant and AI settings routes — agent reasoning lives in adk_engine.py."""

from fastapi import APIRouter
from starlette.requests import Request

from adk_engine import DEFAULT_GEMINI_MODEL, get_agent_reply, reset_session
from ai_engine import (
    DEFAULT_BYOK_BASE_URL,
    DEFAULT_BYOK_MODEL,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    ollama_status,
)
from database import db
from helpers import _require_role_profile
from i18n import _
from models import AIChatMessage, AISettings
from templating import render
from webcompat import flash, login_required, redirect, url_for

router = APIRouter()


def _get_ai_settings(role_profile):
    return AISettings.query.filter_by(role_profile_id=role_profile.id).first()


@router.api_route("/ai-assistant", methods=["GET", "POST"], name="ai_assistant")
@login_required
async def ai_assistant(request: Request):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    if request.method == "POST":
        form = await request.form()
        if form.get("action") == "clear":
            AIChatMessage.query.filter_by(role_profile_id=role_profile.id).delete()
            db.session.commit()
            await reset_session(role_profile)
            return redirect(url_for("ai_assistant"))

        user_text = form.get("message", "").strip()
        if user_text:
            db.session.add(
                AIChatMessage(role_profile_id=role_profile.id, role="user", content=user_text)
            )
            db.session.commit()

            settings = _get_ai_settings(role_profile)
            reply, error = await get_agent_reply(role_profile, settings, user_text)
            if error:
                flash(error, "warning")
                reply = reply or _(
                    "Sorry, I couldn't reach the AI provider. Check your AI settings and try again."
                )
            db.session.add(
                AIChatMessage(role_profile_id=role_profile.id, role="assistant", content=reply)
            )
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

    return render(
        request,
        "ai_assistant.html",
        role_profile=role_profile,
        chat_messages=chat_messages,
        provider=provider,
        ollama_running=is_running,
        ollama_error=ollama_error,
        show_sidebar=True,
    )


@router.api_route("/ai-assistant/feedback", methods=["POST"], name="ai_assistant_feedback")
@login_required
async def ai_assistant_feedback(request: Request):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    form = await request.form()
    rating = form.get("rating")
    try:
        message_id = int(form.get("message_id", ""))
    except ValueError:
        return redirect(url_for("ai_assistant"))

    if rating in ("up", "down"):
        message = AIChatMessage.query.filter_by(
            id=message_id, role_profile_id=role_profile.id, role="assistant"
        ).first()
        if message:
            message.feedback = rating
            db.session.commit()
    return redirect(url_for("ai_assistant"))


@router.api_route("/ai-settings", methods=["GET", "POST"], name="ai_settings")
@login_required
async def ai_settings(request: Request):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    settings = _get_ai_settings(role_profile)

    if request.method == "POST":
        form = await request.form()
        action = form.get("action", "save")
        if settings is None:
            settings = AISettings(role_profile_id=role_profile.id)
            db.session.add(settings)

        settings.provider = form.get("provider", "ollama")
        settings.ollama_host = form.get("ollama_host", "").strip() or DEFAULT_OLLAMA_HOST
        settings.ollama_model = form.get("ollama_model", "").strip() or DEFAULT_OLLAMA_MODEL
        settings.byok_base_url = form.get("byok_base_url", "").strip() or DEFAULT_BYOK_BASE_URL
        settings.byok_model = form.get("byok_model", "").strip() or DEFAULT_BYOK_MODEL
        settings.gemini_model = form.get("gemini_model", "").strip() or DEFAULT_GEMINI_MODEL

        new_key = form.get("byok_api_key", "").strip()
        if new_key:
            settings.byok_api_key = new_key
        elif form.get("clear_byok_key") == "1":
            settings.byok_api_key = None

        new_gemini_key = form.get("gemini_api_key", "").strip()
        if new_gemini_key:
            settings.gemini_api_key = new_gemini_key
        elif form.get("clear_gemini_key") == "1":
            settings.gemini_api_key = None

        db.session.commit()

        if action == "test":
            is_running, models, error = ollama_status(settings.ollama_host)
            if is_running:
                flash(
                    _(
                        "Connected to Ollama at %(host)s. Installed models: %(models)s",
                        host=settings.ollama_host,
                        models=", ".join(models) or str(_("none")),
                    ),
                    "success",
                )
            else:
                flash(
                    _(
                        "Could not reach Ollama at %(host)s: %(error)s",
                        host=settings.ollama_host,
                        error=error,
                    ),
                    "danger",
                )
        else:
            flash(_("AI settings saved."), "success")

        return redirect(url_for("ai_settings"))

    provider = settings.provider if settings else "ollama"
    ollama_host = settings.ollama_host if settings and settings.ollama_host else DEFAULT_OLLAMA_HOST
    ollama_model = (
        settings.ollama_model if settings and settings.ollama_model else DEFAULT_OLLAMA_MODEL
    )
    byok_base_url = (
        settings.byok_base_url if settings and settings.byok_base_url else DEFAULT_BYOK_BASE_URL
    )
    byok_model = settings.byok_model if settings and settings.byok_model else DEFAULT_BYOK_MODEL
    has_byok_key = bool(settings and settings.byok_api_key)
    gemini_model = (
        settings.gemini_model if settings and settings.gemini_model else DEFAULT_GEMINI_MODEL
    )
    has_gemini_key = bool(settings and settings.gemini_api_key)

    is_running, available_models, ollama_error = ollama_status(ollama_host)

    return render(
        request,
        "ai_settings.html",
        role_profile=role_profile,
        provider=provider,
        ollama_host=ollama_host,
        ollama_model=ollama_model,
        byok_base_url=byok_base_url,
        byok_model=byok_model,
        has_byok_key=has_byok_key,
        gemini_model=gemini_model,
        has_gemini_key=has_gemini_key,
        ollama_running=is_running,
        available_models=available_models,
        ollama_error=ollama_error,
        show_sidebar=True,
    )
