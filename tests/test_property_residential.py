def test_residential_owner_flow(logged_in_client):
    from database import SessionLocal
    from models import ParkingSlot, Property

    client = logged_in_client

    response = client.post(
        "/property-setup",
        data={"property_type": "apartment"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert "/property-form" in response.headers["Location"]

    response = client.post(
        "/property-form",
        data={
            "property_type": "apartment",
            "name": "Test Apartments",
            "address": "123 Test Street",
            "num_flats": "10",
            "extra_parking": "2",
        },
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert "/invite-links" in response.headers["Location"]

    prop = Property.query.filter_by(name="Test Apartments").first()
    assert prop is not None
    assert ParkingSlot.query.filter_by(property_id=prop.id).count() == 12
    SessionLocal.remove()

    response = client.post(
        "/role-selection",
        data={"role": "owner"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert "/role-form/owner" in response.headers["Location"]

    response = client.post(
        "/role-form/owner",
        data={
            "name": "Jane Owner",
            "phone": "9000000001",
            "flat_no": "A-101",
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
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert "/dashboard" in response.headers["Location"]

    for path in (
        "/dashboard",
        "/rooms",
        "/parking-slots",
        "/parking-map",
        "/notifications",
        "/my-profile",
    ):
        response = client.get(path)
        assert response.status_code == 200, f"{path} returned {response.status_code}"
