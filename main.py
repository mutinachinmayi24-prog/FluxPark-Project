"""FastAPI application entrypoint: middleware, static files, routers, startup.

Lift-and-shift of the former Flask app — see database.py / i18n.py /
webcompat.py / templating.py for the shims that keep models.py,
parking_engine.py, and the Jinja2 templates working largely unchanged.
"""

import os

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles

from database import Base, SessionLocal, engine
from i18n import current_locale, resolve_locale
from webcompat import current_request

# Import models so all tables are registered on Base.metadata before create_all().
import models  # noqa: F401, E402

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
    secret_key=os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production"),
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
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
