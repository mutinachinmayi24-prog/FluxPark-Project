from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


# -------------------------
# USERS
# -------------------------
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    email = db.Column(db.String(120), unique=True, nullable=True)
    phone = db.Column(db.String(20), unique=True, nullable=True)

    verified = db.Column(db.Boolean, default=False)

    # OWNER / TENANT / COMMITTEE / SECURITY
    role = db.Column(db.String(50))

    created_at = db.Column(db.DateTime, server_default=db.func.now())


# -------------------------
# PROPERTIES
# -------------------------
class Property(db.Model):
    __tablename__ = "properties"

    id = db.Column(db.Integer, primary_key=True)

    property_name = db.Column(db.String(200), nullable=False)

    # Apartment / Gated Community / Office
    property_type = db.Column(db.String(50), nullable=False)

    address = db.Column(db.Text, nullable=False)

    total_units = db.Column(db.Integer, nullable=False)

    extra_parking = db.Column(db.Integer, default=0)

    invite_code = db.Column(db.String(100), unique=True)

    created_at = db.Column(db.DateTime, server_default=db.func.now())


# -------------------------
# OWNERS
# -------------------------
class Owner(db.Model):
    __tablename__ = "owners"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False)

    phone = db.Column(db.String(20), nullable=False)

    flat_no = db.Column(db.String(20), nullable=False)

    parking_slots = db.Column(db.Integer, default=0)

    parking_space_numbers = db.Column(db.String(200))

    created_at = db.Column(db.DateTime, server_default=db.func.now())


# -------------------------
# TENANTS
# -------------------------
class Tenant(db.Model):
    __tablename__ = "tenants"

    id = db.Column(db.Integer, primary_key=True)

    owner_name = db.Column(db.String(100))

    owner_phone = db.Column(db.String(20))

    tenant_name = db.Column(db.String(100))

    tenant_phone = db.Column(db.String(20))

    flat_no = db.Column(db.String(20))

    parking_slots = db.Column(db.Integer)

    parking_space_numbers = db.Column(db.String(200))

    created_at = db.Column(db.DateTime, server_default=db.func.now())


# -------------------------
# COMMITTEE
# -------------------------
class Committee(db.Model):
    __tablename__ = "committee"

    id = db.Column(db.Integer, primary_key=True)

    head_name = db.Column(db.String(100))

    phone = db.Column(db.String(20))

    flat_no = db.Column(db.String(20))

    commission_percent = db.Column(db.Float)

    bank_name = db.Column(db.String(100))

    branch_name = db.Column(db.String(100))

    ifsc_code = db.Column(db.String(20))

    account_number = db.Column(db.String(50))

    created_at = db.Column(db.DateTime, server_default=db.func.now())


# -------------------------
# SECURITY
# -------------------------
class Security(db.Model):
    __tablename__ = "security"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100))

    phone = db.Column(db.String(20))

    shift = db.Column(db.String(50))

    created_at = db.Column(db.DateTime, server_default=db.func.now())