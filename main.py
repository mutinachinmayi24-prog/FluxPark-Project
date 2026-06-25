"""FastAPI application entrypoint: middleware, static files, routers, startup.

Lift-and-shift of the former Flask app — see database.py / i18n.py /
webcompat.py / templating.py for the shims that keep models.py,
parking_engine.py, and the Jinja2 templates working largely unchanged.
"""

import os

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

# Import models so all tables are registered on Base.metadata before create_all().
import models  # noqa: F401  # pylint: disable=unused-import
from database import Base, SessionLocal, engine
from i18n import current_locale, resolve_locale
from routers import (
    ai,
    auth,
    dashboard,
    members,
    notifications,
    onboarding,
    parking,
    payments,
    security,
    transport,
    visitors,
)
from webcompat import current_request

app = FastAPI(title="FluxPark")


async def request_context_middleware(request, call_next):
    request_token = current_request.set(request)
    locale_token = current_locale.set(resolve_locale(request))
    try:
        return await call_next(request)
    finally:
        current_request.reset(request_token)
        current_locale.reset(locale_token)
        SessionLocal.remove()


# Order matters: the LAST middleware added runs FIRST (outermost), so
# SessionMiddleware must be added after request_context_middleware in order
# to populate request.session before resolve_locale() reads it.
app.add_middleware(BaseHTTPMiddleware, dispatch=request_context_middleware)
app.add_middleware(
    SessionMiddleware,
    # dev-only fallback; render.yaml generates a real SECRET_KEY for deployments.
    secret_key=os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production"),  # nosemgrep
)
# Outermost middleware: rejects requests with a spoofed Host header before
# anything else runs, so request.url_for(..., _external=True) (visitor/
# transport pass links, invite links) can't be tricked into building a URL
# pointing at an attacker-controlled domain. Set ALLOWED_HOSTS in production
# (comma-separated); "*" keeps local/dev/Docker-smoke-test usage unrestricted.
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=os.environ.get("ALLOWED_HOSTS", "*").split(","),
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/service-worker.js", include_in_schema=False)
def service_worker():
    # Served at the site root (not /static/...) so its default scope covers
    # the whole app -- a service worker can only control paths at or below
    # its own location unless the server sends Service-Worker-Allowed.
    return FileResponse("static/js/service-worker.js", media_type="application/javascript")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(onboarding.router)
app.include_router(dashboard.router)
app.include_router(parking.router)
app.include_router(visitors.router)
app.include_router(transport.router)
app.include_router(security.router)
app.include_router(members.router)
app.include_router(notifications.router)
app.include_router(payments.router)
app.include_router(ai.router)
