from flask_babel import lazy_gettext as _l

PROPERTY_TYPES = [
    ("apartment", _l("Apartment")),
    ("gated_community", _l("Gated Community")),
    ("office", _l("Office")),
]

RESIDENTIAL_PROPERTY_TYPES = ("apartment", "gated_community")

RESIDENTIAL_ROLES = [
    ("owner", _l("Owner")),
    ("tenant", _l("Tenant")),
    ("committee", _l("Committee")),
    ("security", _l("Security")),
]

OFFICE_ROLES = [
    ("employee", _l("Employee")),
    ("security", _l("Security")),
    ("manager", _l("Manager")),
]

ROLE_LABELS = {
    "owner": _l("Owner"),
    "tenant": _l("Tenant"),
    "committee": _l("Committee"),
    "security": _l("Security"),
    "employee": _l("Employee"),
    "manager": _l("Manager"),
}

PROPERTY_TYPE_LABELS = {
    "apartment": _l("Apartment"),
    "gated_community": _l("Gated Community"),
    "office": _l("Office"),
}

VEHICLE_TYPES = ["Bike", "Car", "Auto", "Truck", "Camper", "Cycle", "Other"]

VEHICLE_TYPE_LABELS = {
    "Bike": _l("Bike"),
    "Car": _l("Car"),
    "Auto": _l("Auto"),
    "Truck": _l("Truck"),
    "Camper": _l("Camper"),
    "Cycle": _l("Cycle"),
    "Other": _l("Other"),
}

OTP_VALIDITY_MINUTES = 5
