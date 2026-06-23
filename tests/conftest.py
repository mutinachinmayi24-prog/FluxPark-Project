import contextlib
import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def app_module():
    """Import the FastAPI app bound to a throwaway SQLite database."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ.setdefault("SECRET_KEY", "test-secret-key")

    import main as flux_main

    yield flux_main

    from database import SessionLocal, engine

    SessionLocal.remove()
    engine.dispose()

    with contextlib.suppress(OSError):
        os.remove(db_path)


@pytest.fixture()
def client(app_module):
    with TestClient(app_module.app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_database(app_module):
    yield
    from database import Base, SessionLocal, engine

    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    SessionLocal.remove()


@pytest.fixture()
def logged_in_client(client):
    """A test client that has completed signup + OTP verification."""
    from database import SessionLocal
    from models import OTPRequest

    client.post("/signup", data={"contact_type": "phone", "contact": "9000000001"})
    otp = OTPRequest.query.filter_by(contact="9000000001").order_by(OTPRequest.id.desc()).first()
    code = otp.code
    SessionLocal.remove()

    client.post("/verify-otp", data={"code": code})
    return client
