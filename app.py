from flask import Flask, render_template, request, session, redirect, url_for
from models import (
    db,
    Property,
    Owner,
    Tenant,
    Committee,
    Security,
    VisitorRequest,
    ParkingAvailability
)

import random
import uuid

app = Flask(__name__)

# ====================================
# CONFIG
# ====================================

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "fluxpark-secret"

db.init_app(app)

with app.app_context():
    db.create_all()


# ====================================
# HOME / LOGIN
# ====================================

@app.route("/")
def home():
    return render_template("login.html")


# ====================================
# OTP (SIMULATION)
# ====================================

@app.route("/send-otp", methods=["POST"])
def send_otp():
    contact = request.form["contact"]
    otp = str(random.randint(100000, 999999))

    session["otp"] = otp
    session["contact"] = contact

    print("\nOTP:", otp)

    return render_template("verify_otp.html")


@app.route("/verify-otp", methods=["POST"])
def verify_otp():
    entered = request.form["otp"]

    if entered == session.get("otp"):
        return redirect("/property-setup")

    return "<h3>Wrong OTP</h3><a href='/'>Try Again</a>"


# ====================================
# PROPERTY
# ====================================

@app.route("/property-setup")
def property_setup():
    return render_template("property_setup.html")


@app.route("/create-property", methods=["POST"])
def create_property():

    property_obj = Property(
        property_name=request.form["property_name"],
        property_type=request.form["property_type"],
        address=request.form["address"],
        total_units=request.form["total_units"],
        extra_parking=request.form["extra_parking"],
        invite_code=str(uuid.uuid4())[:8]
    )

    db.session.add(property_obj)
    db.session.commit()

    link = f"http://127.0.0.1:5000/join/{property_obj.invite_code}"

    return render_template("property_created.html", invite_link=link)


# ====================================
# JOIN PROPERTY
# ====================================

@app.route("/join/<code>")
def join(code):

    property_obj = Property.query.filter_by(invite_code=code).first()

    if not property_obj:
        return "Invalid Invite Link"

    session["invite_code"] = code

    return redirect("/select-role/" + code)


# ====================================
# ROLE SELECTION
# ====================================

@app.route("/select-role/<code>", methods=["GET", "POST"])
def select_role(code):

    if request.method == "POST":
        role = request.form["role"]

        if role == "owner":
            return redirect("/owner-form")
        if role == "tenant":
            return redirect("/tenant-form")
        if role == "committee":
            return redirect("/committee-form")
        if role == "security":
            return redirect("/security-form")

    return render_template("role_selection.html")


# ====================================
# OWNER
# ====================================

@app.route("/owner-form")
def owner_form():
    return render_template("owner_form.html")


@app.route("/save-owner", methods=["POST"])
def save_owner():

    owner = Owner(
        name=request.form["name"],
        phone=request.form["phone"],
        flat_no=request.form["flat_no"],
        parking_slots=request.form["parking_slots"],
        parking_space_numbers=request.form["parking_space_numbers"]
    )

    db.session.add(owner)
    db.session.commit()

    return redirect("/dashboard")


# ====================================
# TENANT
# ====================================

@app.route("/tenant-form")
def tenant_form():
    return render_template("tenant_form.html")


@app.route("/save-tenant", methods=["POST"])
def save_tenant():

    tenant = Tenant(
        owner_name=request.form["owner_name"],
        owner_phone=request.form["owner_phone"],
        tenant_name=request.form["tenant_name"],
        tenant_phone=request.form["tenant_phone"],
        flat_no=request.form["flat_no"],
        parking_slots=request.form["parking_slots"],
        parking_space_numbers=request.form["parking_space_numbers"]
    )

    db.session.add(tenant)
    db.session.commit()

    return redirect("/dashboard")


# ====================================
# COMMITTEE
# ====================================

@app.route("/committee-form")
def committee_form():
    return render_template("committee_form.html")


@app.route("/save-committee", methods=["POST"])
def save_committee():

    committee = Committee(
        head_name=request.form["head_name"],
        phone=request.form["phone"],
        flat_no=request.form["flat_no"],
        commission_percent=request.form["commission_percent"],
        bank_name=request.form["bank_name"],
        branch_name=request.form["branch_name"],
        ifsc_code=request.form["ifsc_code"],
        account_number=request.form["account_number"]
    )

    db.session.add(committee)
    db.session.commit()

    return redirect("/dashboard")


# ====================================
# SECURITY
# ====================================

@app.route("/security-form")
def security_form():
    return render_template("security_form.html")


@app.route("/save-security", methods=["POST"])
def save_security():

    security = Security(
        name=request.form["name"],
        phone=request.form["phone"],
        shift=request.form["shift"]
    )

    db.session.add(security)
    db.session.commit()

    return redirect("/dashboard")


# ====================================
# VISITOR PAGE
# ====================================

@app.route("/visitor-request")
def visitor_request():
    return render_template("visitor_request.html")


@app.route("/create-visitor-request", methods=["POST"])
def create_visitor_request():

    visitor = VisitorRequest(
        visitor_name=request.form["visitor_name"],
        visitor_phone=request.form["phone"],
        vehicle_number=request.form["vehicle_number"],
        status="Pending"
    )

    db.session.add(visitor)
    db.session.commit()

    return render_template("visitor_pass.html", visitor=visitor)


# ====================================
# PARKING PAGE
# ====================================

@app.route("/parking")
def parking():

    slots = ParkingAvailability.query.all()

    return render_template(
        "parking_availability.html",
        slots=slots
    )


@app.route("/create-parking-slot", methods=["POST"])
def create_parking_slot():

    slot = ParkingAvailability(
        owner_name=request.form["owner_name"],
        flat_no=request.form["flat_no"],
        slot_number=request.form["slot_number"],
        available_date=request.form["available_date"],
        from_time=request.form["from_time"],
        to_time=request.form["to_time"],
        rent_per_hour=request.form["rent_per_hour"]
    )

    db.session.add(slot)
    db.session.commit()

    return redirect("/parking")


# ====================================
# DASHBOARD
# ====================================

@app.route("/dashboard")
def dashboard():

    total_members = (
        Owner.query.count()
        + Tenant.query.count()
        + Security.query.count()
        + Committee.query.count()
    )

    return render_template(
        "dashboard.html",
        total_members=total_members
    )


# ====================================
# RUN
# ====================================

if __name__ == "__main__":
    app.run(debug=True)