"""SQLAlchemy engine/session setup and a Flask-SQLAlchemy-style `db` namespace.

`Base.query = SessionLocal.query_property()` keeps `Model.query.filter_by(...)`
/ `.get(...)` working unchanged in models.py and parking_engine.py. Table names
are derived from class names with Flask-SQLAlchemy's CamelCase -> snake_case
convention, so the foreign-key strings already in models.py ("user.id",
"role_profile.id", etc.) keep resolving correctly without any changes there.
"""

import contextvars
import os
import re
from types import SimpleNamespace

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    create_engine,
    func,
    or_,
)
from sqlalchemy.orm import (
    backref,
    declarative_base,
    declared_attr,
    relationship,
    scoped_session,
    sessionmaker,
)

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///instance/database.db")

if DATABASE_URL.startswith("sqlite:///") and DATABASE_URL not in ("sqlite:///:memory:",):
    db_path = DATABASE_URL.removeprefix("sqlite:///")
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

# Scope sessions per asyncio task (not per thread): route handlers are `async
# def` and may `await` (e.g. request.form()), so concurrent requests can
# interleave on the same OS thread. A contextvar-based scope keeps each
# request's session isolated; the request-teardown middleware calls
# SessionLocal.remove() to discard it.
_session_scope: contextvars.ContextVar = contextvars.ContextVar("session_scope")


def _scopefunc():
    try:
        return _session_scope.get()
    except LookupError:
        token = object()
        _session_scope.set(token)
        return token


SessionLocal = scoped_session(  # pylint: disable=invalid-name
    sessionmaker(bind=engine, autoflush=True, autocommit=False), scopefunc=_scopefunc
)

_CAMEL_RE = re.compile(r"((?<=[a-z0-9])[A-Z]|(?!^)[A-Z](?=[a-z]))")


class _BaseModel:
    @declared_attr
    def __tablename__(cls):  # noqa: N805  # pylint: disable=no-self-argument
        return _CAMEL_RE.sub(r"_\1", cls.__name__).lower().lstrip("_")  # pylint: disable=no-member


Base = declarative_base(cls=_BaseModel)
Base.query = SessionLocal.query_property()


db = SimpleNamespace(
    Model=Base,
    Column=Column,
    Integer=Integer,
    String=String,
    Text=Text,
    Boolean=Boolean,
    Float=Float,
    Date=Date,
    Time=Time,
    DateTime=DateTime,
    JSON=JSON,
    ForeignKey=ForeignKey,
    UniqueConstraint=UniqueConstraint,
    relationship=relationship,
    backref=backref,
    func=func,
    or_=or_,
    session=SessionLocal,
)
