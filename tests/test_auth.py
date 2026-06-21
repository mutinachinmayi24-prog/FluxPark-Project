def test_index_redirects_to_signup(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert "/signup" in response.headers["Location"]


def test_signup_page_loads(client):
    response = client.get("/signup")
    assert response.status_code == 200


def test_signup_rejects_invalid_phone(client):
    from models import OTPRequest
    from database import SessionLocal

    response = client.post(
        "/signup",
        data={"contact_type": "phone", "contact": "123"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"valid 10-digit mobile number" in response.content

    assert OTPRequest.query.count() == 0
    SessionLocal.remove()


def test_set_language(client):
    response = client.get("/set-language/hi", follow_redirects=False)
    assert response.status_code in (302, 307)
    # Language stored in session cookie — verify subsequent request uses it
    follow = client.get("/signup")
    assert follow.status_code == 200


def test_dashboard_requires_login(client):
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert "/signup" in response.headers["Location"]


def test_signup_and_verify_otp_creates_user(client):
    from models import OTPRequest, User
    from database import SessionLocal

    response = client.post(
        "/signup",
        data={"contact_type": "phone", "contact": "9000000002"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert "/verify-otp" in response.headers["Location"]

    otp = (
        OTPRequest.query.filter_by(contact="9000000002")
        .order_by(OTPRequest.id.desc())
        .first()
    )
    assert otp is not None
    code = otp.code
    SessionLocal.remove()

    # Wrong code is rejected.
    wrong_code = "000000" if code != "000000" else "111111"
    response = client.post("/verify-otp", data={"code": wrong_code}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Incorrect OTP" in response.content

    # Correct code succeeds and routes to property setup for a brand-new user.
    response = client.post("/verify-otp", data={"code": code}, follow_redirects=False)
    assert response.status_code in (302, 307)
    assert "/property-setup" in response.headers["Location"]

    user = User.query.filter_by(phone="9000000002").first()
    assert user is not None
    SessionLocal.remove()
