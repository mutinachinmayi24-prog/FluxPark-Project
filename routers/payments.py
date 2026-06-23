"""Payments list and mark-paid routes."""

from fastapi import APIRouter
from starlette.requests import Request

from constants import RESIDENTIAL_PROPERTY_TYPES
from database import db
from helpers import _require_role_profile, _role_profile_label
from i18n import _
from models import Property, Transaction
from parking_engine import notify
from templating import render
from webcompat import abort, flash, login_required, redirect, url_for

router = APIRouter()


@router.api_route("/payments", methods=["GET"], name="payments")
@login_required
async def payments(request: Request):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp
    if role_profile.role not in ("owner", "tenant", "committee", "manager"):
        abort(403)

    prop = Property.query.get(role_profile.property_id)
    is_office = prop.property_type not in RESIDENTIAL_PROPERTY_TYPES

    payable = (
        Transaction.query.filter_by(payer_role_profile_id=role_profile.id)
        .filter(Transaction.status != "cancelled")
        .order_by(Transaction.created_at.desc())
        .all()
    )
    receivable = (
        Transaction.query.filter_by(payee_role_profile_id=role_profile.id)
        .filter(Transaction.status != "cancelled")
        .order_by(Transaction.created_at.desc())
        .all()
    )

    commission_total = None
    if role_profile.role == "committee":
        commission_total = (
            db.session.query(db.func.sum(Transaction.commission_amount))
            .filter(
                Transaction.property_id == role_profile.property_id,
                Transaction.status != "cancelled",
            )
            .scalar()
            or 0
        )

    return render(
        request,
        "payments.html",
        role_profile=role_profile,
        property=prop,
        is_office=is_office,
        payable=payable,
        receivable=receivable,
        commission_total=commission_total,
        role_profile_label=_role_profile_label,
        show_sidebar=True,
    )


@router.api_route(
    "/payments/{transaction_id}/mark-paid", methods=["POST"], name="mark_payment_paid"
)
@login_required
async def mark_payment_paid(request: Request, transaction_id: int):
    role_profile, redirect_resp = _require_role_profile()
    if redirect_resp:
        return redirect_resp

    txn = Transaction.query.get(transaction_id)
    if txn is None:
        abort(404)
    if txn.payer_role_profile_id != role_profile.id:
        abort(403)
    if txn.status != "pending":
        flash(_("This payment has already been processed."), "warning")
        return redirect(url_for("payments"))

    txn.status = "paid"
    notify(
        txn.payee_role_profile_id,
        "Payment received",
        f"{_role_profile_label(role_profile)} marked a payment of ₹{txn.total_amount} as paid "
        f"for {txn.description}.",
    )
    db.session.commit()
    flash(_("Marked as paid."), "success")
    return redirect(url_for("payments"))
