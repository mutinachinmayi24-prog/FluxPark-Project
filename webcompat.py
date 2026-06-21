"""Flask-parity helpers shared by templates, routers, and parking_engine.py.

`current_request` is set by middleware (see main.py) at the start of every
request, which lets `url_for`, `session`, `flash`, etc. behave like Flask's
request-bound globals without threading `request` through every call site.
"""

import urllib.parse
from contextvars import ContextVar
from functools import wraps

from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse

current_request: ContextVar[Request] = ContextVar("current_request")


# ---------------------------------------------------------------------------
# url_for
# ---------------------------------------------------------------------------


def _route_param_names(app, name):
    def _search(routes):
        for route in routes:
            if getattr(route, "name", None) == name:
                convertors = getattr(route, "param_convertors", None)
                return set(convertors.keys()) if convertors else set()
            nested = None
            if hasattr(route, "original_router"):
                nested = route.original_router.routes
            elif hasattr(route, "routes"):
                nested = route.routes
            if nested:
                result = _search(nested)
                if result is not None:
                    return result
        return None

    return _search(app.router.routes) or set()


def url_for(name, **kwargs):
    """Flask-style url_for: extra kwargs become a query string.

    Unlike Starlette's `request.url_for()` (which only fills path params and
    raises on unexpected ones), this also special-cases `static` -> the
    StaticFiles mount, and silently drops `_external` since Starlette URLs
    are already absolute.
    """
    request = current_request.get()
    app = request.app
    kwargs.pop("_external", None)

    if name == "static":
        path_kwargs = {"path": kwargs.pop("filename", "")}
    else:
        param_names = _route_param_names(app, name)
        path_kwargs = {k: kwargs.pop(k) for k in list(kwargs) if k in param_names}

    url = str(request.url_for(name, **path_kwargs))
    query = {k: v for k, v in kwargs.items() if v is not None}
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    return url


# ---------------------------------------------------------------------------
# session
# ---------------------------------------------------------------------------


class _SessionProxy:
    """Proxies to the current request's Starlette session (cookie-based)."""

    def __getattr__(self, name):
        return getattr(current_request.get().session, name)

    def __getitem__(self, key):
        return current_request.get().session[key]

    def __setitem__(self, key, value):
        current_request.get().session[key] = value

    def __delitem__(self, key):
        del current_request.get().session[key]

    def __contains__(self, key):
        return key in current_request.get().session

    def get(self, key, default=None):
        return current_request.get().session.get(key, default)

    def pop(self, key, default=None):
        return current_request.get().session.pop(key, default)

    def clear(self):
        current_request.get().session.clear()


session = _SessionProxy()


# ---------------------------------------------------------------------------
# flash / get_flashed_messages
# ---------------------------------------------------------------------------


def flash(message, category="message"):
    request = current_request.get()
    flashes = request.session.setdefault("_flashes", [])
    flashes.append((category, str(message)))


def get_flashed_messages(with_categories=False, category_filter=()):
    request = current_request.get()
    flashes = request.session.pop("_flashes", [])
    if category_filter:
        flashes = [f for f in flashes if f[0] in category_filter]
    if with_categories:
        return flashes
    return [message for _category, message in flashes]


# ---------------------------------------------------------------------------
# redirect / abort
# ---------------------------------------------------------------------------


def redirect(url, status_code=302):
    return RedirectResponse(url, status_code=status_code)


def abort(status_code, detail=None):
    raise HTTPException(status_code=status_code, detail=detail)


# ---------------------------------------------------------------------------
# login_required
# ---------------------------------------------------------------------------


def login_required(view):
    @wraps(view)
    async def wrapped(request: Request, *args, **kwargs):
        if not request.session.get("user_id"):
            return redirect(url_for("signup"))
        return await view(request, *args, **kwargs)

    return wrapped


# ---------------------------------------------------------------------------
# get_or_404 / first_or_404
# ---------------------------------------------------------------------------


def get_or_404(model, ident):
    obj = model.query.get(ident)
    if obj is None:
        raise HTTPException(status_code=404)
    return obj


def first_or_404(query):
    obj = query.first()
    if obj is None:
        raise HTTPException(status_code=404)
    return obj
