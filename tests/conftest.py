import os
import tempfile

import pytest


@pytest.fixture(scope="session")
def app_module():
    """Import the Flask app bound to a throwaway SQLite database.

    app.py reads DATABASE_URL (falling back to instance/database.db) and
    runs db.create_all() at import time, so the env var must be set before
    the first import.
    """
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ.setdefault("SECRET_KEY", "test-secret-key")

    import app as flux_app

    flux_app.app.config.update(TESTING=True)

    yield flux_app

    with flux_app.app.app_context():
        flux_app.db.session.remove()
        flux_app.db.engine.dispose()

    try:
        os.remove(db_path)
    except OSError:
        pass


@pytest.fixture()
def client(app_module):
    return app_module.app.test_client()


@pytest.fixture(autouse=True)
def _clean_database(app_module):
    yield
    with app_module.app.app_context():
        for table in reversed(app_module.db.metadata.sorted_tables):
            app_module.db.session.execute(table.delete())
        app_module.db.session.commit()


@pytest.fixture()
def logged_in_client(client, app_module):
    """A test client that has completed signup + OTP verification."""
    from models import OTPRequest

    client.post("/signup", data={"contact_type": "phone", "contact": "9000000001"})
    with app_module.app.app_context():
        otp = OTPRequest.query.filter_by(contact="9000000001").order_by(OTPRequest.id.desc()).first()
        code = otp.code
    client.post("/verify-otp", data={"code": code})
    return client
