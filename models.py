from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Property(db.Model):
    __tablename__ = "properties"

    id = db.Column(db.Integer, primary_key=True)

    property_name = db.Column(db.String(200))
    property_type = db.Column(db.String(50))
    address = db.Column(db.Text)

    total_units = db.Column(db.Integer)
    extra_parking = db.Column(db.Integer)

    invite_code = db.Column(db.String(100), unique=True)


class Owner(db.Model):
    __tablename__ = "owners"

    id = db.Column(db.Integer, primary_key=True)

    property_id = db.Column(
        db.Integer,
        db.ForeignKey("properties.id")
    )

    name = db.Column(db.String(100))
    phone = db.Column(db.String(20))

    flat_no = db.Column(db.String(20))

    parking_slots = db.Column(db.Integer)

    parking_space_numbers = db.Column(db.String(200))


class Tenant(db.Model):
    __tablename__ = "tenants"

    id = db.Column(db.Integer, primary_key=True)

    property_id = db.Column(
        db.Integer,
        db.ForeignKey("properties.id")
    )

    owner_name = db.Column(db.String(100))
    owner_phone = db.Column(db.String(20))

    tenant_name = db.Column(db.String(100))
    tenant_phone = db.Column(db.String(20))

    flat_no = db.Column(db.String(20))

    parking_slots = db.Column(db.Integer)

    parking_space_numbers = db.Column(db.String(200))


class Committee(db.Model):
    __tablename__ = "committee"

    id = db.Column(db.Integer, primary_key=True)

    property_id = db.Column(
        db.Integer,
        db.ForeignKey("properties.id")
    )

    head_name = db.Column(db.String(100))

    phone = db.Column(db.String(20))

    flat_no = db.Column(db.String(20))

    commission_percent = db.Column(db.Float)

    bank_name = db.Column(db.String(100))

    branch_name = db.Column(db.String(100))

    ifsc_code = db.Column(db.String(20))

    account_number = db.Column(db.String(50))


class Security(db.Model):
    __tablename__ = "security"

    id = db.Column(db.Integer, primary_key=True)

    property_id = db.Column(
        db.Integer,
        db.ForeignKey("properties.id")
    )

    name = db.Column(db.String(100))

    phone = db.Column(db.String(20))

    shift = db.Column(db.String(50))