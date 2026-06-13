def test_index_redirects_to_signup(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/signup" in response.headers["Location"]


def test_signup_page_loads(client):
    response = client.get("/signup")
    assert response.status_code == 200


def test_signup_rejects_invalid_phone(client, app_module):
    from models import OTPRequest

    response = client.post(
        "/signup",
        data={"contact_type": "phone", "contact": "123"},
    )
    assert response.status_code == 200
    assert b"valid 10-digit mobile number" in response.data

    with app_module.app.app_context():
        assert OTPRequest.query.count() == 0


def test_set_language(client):
    response = client.get("/set-language/hi", follow_redirects=False)
    assert response.status_code == 302

    with client.session_transaction() as session:
        assert session["lang"] == "hi"


def test_dashboard_requires_login(client):
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/signup" in response.headers["Location"]


def test_signup_and_verify_otp_creates_user(client, app_module):
    from models import OTPRequest, User

    response = client.post(
        "/signup",
        data={"contact_type": "phone", "contact": "9000000002"},
    )
    assert response.status_code == 302
    assert "/verify-otp" in response.headers["Location"]

    with app_module.app.app_context():
        otp = (
            OTPRequest.query.filter_by(contact="9000000002")
            .order_by(OTPRequest.id.desc())
            .first()
        )
        assert otp is not None
        code = otp.code

    # Wrong code is rejected.
    wrong_code = "000000" if code != "000000" else "111111"
    response = client.post("/verify-otp", data={"code": wrong_code})
    assert response.status_code == 200
    assert b"Incorrect OTP" in response.data

    # Correct code succeeds and routes to property setup for a brand-new user.
    response = client.post("/verify-otp", data={"code": code})
    assert response.status_code == 302
    assert "/property-setup" in response.headers["Location"]

    with app_module.app.app_context():
        user = User.query.filter_by(phone="9000000002").first()
        assert user is not None
