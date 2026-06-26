import pytest


def _onboard_owner(client):
    client.post("/property-setup", data={"property_type": "apartment"})
    client.post(
        "/property-form",
        data={
            "property_type": "apartment",
            "name": "AI Test Apartments",
            "address": "1 Test Street",
            "num_flats": "5",
            "extra_parking": "0",
        },
    )
    client.post("/role-selection", data={"role": "owner"})
    client.post(
        "/role-form/owner",
        data={
            "name": "AI Owner",
            "phone": "9000000001",
            "flat_no": "A-1",
            "num_parking_slots": "1",
            "parking_space_number": "P-1",
            "vehicle_type[]": "Car",
            "vehicle_number[]": "KA01AB1234",
            "bank_name": "Test Bank",
            "branch": "Test Branch",
            "ifsc_code": "TEST0001234",
            "account_number": "123456789012",
            "expiry_date": "2030-01-01",
        },
    )


def test_ai_assistant_page_loads(logged_in_client):
    _onboard_owner(logged_in_client)
    response = logged_in_client.get("/ai-assistant")
    assert response.status_code == 200


def test_ai_settings_page_loads_and_saves(logged_in_client):
    _onboard_owner(logged_in_client)
    response = logged_in_client.get("/ai-settings")
    assert response.status_code == 200

    response = logged_in_client.post(
        "/ai-settings",
        data={"action": "save", "provider": "gemini", "gemini_model": "gemini-2.0-flash"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)

    from database import SessionLocal
    from models import AISettings, RoleProfile

    role_profile = RoleProfile.query.first()
    settings = AISettings.query.filter_by(role_profile_id=role_profile.id).first()
    assert settings.provider == "gemini"
    assert settings.gemini_model == "gemini-2.0-flash"
    SessionLocal.remove()


def test_ai_assistant_feedback(logged_in_client):
    _onboard_owner(logged_in_client)

    from database import SessionLocal, db
    from models import AIChatMessage, RoleProfile

    role_profile_id = RoleProfile.query.first().id
    message = AIChatMessage(
        role_profile_id=role_profile_id, role="assistant", content="Test reply."
    )
    db.session.add(message)
    db.session.commit()
    message_id = message.id
    SessionLocal.remove()

    response = logged_in_client.post(
        "/ai-assistant/feedback",
        data={"message_id": str(message_id), "rating": "up"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)

    updated = AIChatMessage.query.get(message_id)
    assert updated.feedback == "up"
    SessionLocal.remove()

    # A user-role message can't be rated even if the ids happen to collide --
    # the route filters on role="assistant" as well as message ownership.
    user_message = AIChatMessage(role_profile_id=role_profile_id, role="user", content="Hi")
    db.session.add(user_message)
    db.session.commit()
    user_message_id = user_message.id
    SessionLocal.remove()

    logged_in_client.post(
        "/ai-assistant/feedback",
        data={"message_id": str(user_message_id), "rating": "down"},
        follow_redirects=False,
    )
    untouched = AIChatMessage.query.get(user_message_id)
    assert untouched.feedback is None
    SessionLocal.remove()


def test_ai_assistant_chat_with_ollama(logged_in_client):
    from ai_engine import ollama_status

    is_running, _models, _error = ollama_status()
    if not is_running:
        pytest.skip("No local Ollama server reachable for a live ADK agent test")

    _onboard_owner(logged_in_client)

    response = logged_in_client.post(
        "/ai-assistant",
        data={"message": "What parking slots do I have?"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    from database import SessionLocal
    from models import AIChatMessage, RoleProfile

    role_profile = RoleProfile.query.first()
    messages = (
        AIChatMessage.query.filter_by(role_profile_id=role_profile.id)
        .order_by(AIChatMessage.id.asc())
        .all()
    )
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"
    assert messages[1].content.strip() != ""
    SessionLocal.remove()

    # Clearing the conversation should remove the transcript and reset agent memory.
    response = logged_in_client.post(
        "/ai-assistant", data={"action": "clear"}, follow_redirects=False
    )
    assert response.status_code in (302, 307)
    assert AIChatMessage.query.filter_by(role_profile_id=role_profile.id).count() == 0
    SessionLocal.remove()
