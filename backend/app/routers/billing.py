"""Subscription billing: plans, Razorpay auto-renew, UPI fallback, invoices, signed webhook."""
import json
import re

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.deps import Workspace, read_ws, require_ws
from ..core.lib import PLANS, ApiError, epoch_ms, notify, notify_admins
from ..core.security import hmac_sha256_hex
from ..core.serialize import to_dict
from ..database import get_db
from ..models import Payment, PlatformSettings
from ..services.razorpay_service import apply_subscription, ensure_plan_id, invoice_no, rzp

router = APIRouter(tags=["billing"])

TERMS = {1: {"label": "1 month", "multiplier": 1}, 3: {"label": "3 months", "multiplier": 3}, 12: {"label": "12 months (2 months free)", "multiplier": 10}}
PAID_PLANS = ("starter", "pro", "agency")


@router.get("/billing/plans")
def plans():
    return PLANS


@router.get("/billing/payment-info")
def payment_info(ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    s = db.scalar(select(PlatformSettings))
    return {"upiId": s.upi_id if s else None, "payeeName": (s.payee_name if s else None) or "SocialGrow AI",
            "supportPhone": s.support_phone if s else None, "terms": TERMS}


@router.get("/billing/gateway-ready")
def gateway_ready(ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    s = db.scalar(select(PlatformSettings))
    return {"ready": bool(s and s.razorpay_key_id and s.razorpay_key_secret)}


@router.get("/billing/invoices")
def invoices(ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    rows = db.scalars(select(Payment).where(Payment.agency_id == ws.agency.id).order_by(Payment.created_at.desc()).limit(50)).all()
    return [to_dict(p, exclude=("razorpay_payment_id", "submitted_by")) for p in rows]


class UpiIn(BaseModel):
    plan: str
    months: int
    reference: str


@router.post("/billing/upi")
def submit_upi_payment(body: UpiIn, ws: Workspace = Depends(require_ws(("owner",), allow_inactive=True)), db: Session = Depends(get_db)):
    if ws.agency.status in ("pending", "rejected"):
        raise ApiError("Account approve hone ke baad hi payment karein.")
    if body.plan not in PAID_PLANS:
        raise ApiError("Plan chunein.")
    term = TERMS.get(body.months)
    if not term:
        raise ApiError("Period chunein.")
    ref = re.sub(r"\s+", "", body.reference.strip().upper())
    if not re.fullmatch(r"[A-Z0-9]{8,30}", ref):
        raise ApiError("Sahi UTR / Transaction ID daalein (UPI app ki payment details mein milta hai).")
    if db.scalar(select(Payment).where(Payment.reference == ref, Payment.status.in_(("pending", "paid")))):
        raise ApiError("Ye UTR pehle se submit ho chuka hai.")
    amount = PLANS[body.plan]["price"] * term["multiplier"]
    db.add(Payment(agency_id=ws.agency.id, plan=body.plan, amount=amount, currency="INR", status="pending", method="UPI", reference=ref,
                   months=body.months, submitted_by=ws.user.id, invoice_no=invoice_no(db, ws.agency.id)))
    notify(db, ws.agency.id, "billing", f"Payment (UTR {ref}) verification ke liye submit hua. Usually kuch ghanton mein verify ho jata hai.")
    notify_admins(db, f"{ws.agency.name} ne ₹{amount:,} ka UPI payment submit kiya (UTR {ref}) — verify karein")
    db.commit()
    return {"ok": True}


# ---------------- Razorpay auto-renew ----------------

def _gateway(db: Session) -> PlatformSettings:
    s = db.scalar(select(PlatformSettings))
    if not s or not s.razorpay_key_id or not s.razorpay_key_secret:
        raise ApiError("Online payment abhi set nahi hai. Support se contact karein.")
    return s


class SubscribeIn(BaseModel):
    plan: str
    cycle: str


@router.post("/billing/subscribe")
def subscribe(body: SubscribeIn, ws: Workspace = Depends(require_ws(("owner",), allow_inactive=True)), db: Session = Depends(get_db)):
    if body.plan not in PAID_PLANS or body.cycle not in ("monthly", "yearly"):
        raise ApiError("Plan chunein.")
    s = _gateway(db)
    a = ws.agency
    live = a.razorpay_subscription_id and (a.razorpay_sub_status or "") in ("active", "authenticated", "pending")
    if live and not a.cancel_at_period_end:
        raise ApiError("Auto-renew pehle se ON hai. Plan badalne ke liye pehle 'Cancel auto-renew' karein.")
    plan_id = ensure_plan_id(db, s, body.plan, body.cycle)
    now = epoch_ms()
    # First charge when the trial / current paid period ends, so customers never pay twice
    start_ms = max(a.trial_ends_at if a.subscription_status == "trialing" and a.trial_ends_at else 0,
                   a.current_period_end if a.subscription_status == "active" and a.current_period_end else 0)
    payload = {"plan_id": plan_id, "total_count": 10 if body.cycle == "yearly" else 120, "quantity": 1, "customer_notify": 1,
               "notes": {"agencyId": a.id, "plan": body.plan, "cycle": body.cycle, "agency": a.name[:200]}}
    if start_ms > now + 5 * 60_000:
        payload["start_at"] = start_ms // 1000
    sub = rzp(s.razorpay_key_id, s.razorpay_key_secret, "POST", "/subscriptions", payload)
    if not sub.get("short_url"):
        raise ApiError("Razorpay se payment link nahi mila.")
    a.razorpay_subscription_id, a.razorpay_sub_status = sub["id"], "created"
    a.pending_plan, a.cancel_at_period_end = f"{body.plan}:{body.cycle}", False
    db.commit()
    return {"url": sub["short_url"]}


@router.post("/billing/sync")
def sync_mine(ws: Workspace = Depends(require_ws(("owner",), allow_inactive=True)), db: Session = Depends(get_db)):
    s = _gateway(db)
    if not ws.agency.razorpay_subscription_id:
        return {"status": "none"}
    sub = rzp(s.razorpay_key_id, s.razorpay_key_secret, "GET", f"/subscriptions/{ws.agency.razorpay_subscription_id}")
    payment = None
    if sub["status"] == "active":
        inv = rzp(s.razorpay_key_id, s.razorpay_key_secret, "GET", f"/invoices?subscription_id={sub['id']}&count=1")
        last = (inv.get("items") or [None])[0]
        if last and last.get("payment_id") and last.get("status") == "paid":
            payment = {"id": last["payment_id"], "amount": last["amount_paid"]}
    apply_subscription(db, "sync", {"id": sub["id"], "status": sub["status"], "current_end": sub.get("current_end"), "notes": sub.get("notes")}, payment)
    return {"status": sub["status"]}


@router.post("/billing/cancel")
def cancel_auto_renew(ws: Workspace = Depends(require_ws(("owner",), allow_inactive=True)), db: Session = Depends(get_db)):
    s = _gateway(db)
    a = ws.agency
    if not a.razorpay_subscription_id:
        raise ApiError("Koi active subscription nahi hai.")
    sub = rzp(s.razorpay_key_id, s.razorpay_key_secret, "POST", f"/subscriptions/{a.razorpay_subscription_id}/cancel",
              {"cancel_at_cycle_end": 1 if a.razorpay_sub_status == "active" else 0})
    apply_subscription(db, "subscription.cancelled", {"id": sub["id"], "status": "cancelled", "current_end": sub.get("current_end"), "notes": sub.get("notes")})
    return {"ok": True}


@router.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """Verifies X-Razorpay-Signature (HMAC-SHA256 of the raw body) before applying subscription events."""
    from fastapi.responses import PlainTextResponse

    body = await request.body()
    s = db.scalar(select(PlatformSettings))
    if not s or not s.razorpay_webhook_secret:
        return PlainTextResponse("webhook secret not configured", status_code=503)
    signature = request.headers.get("x-razorpay-signature", "")
    import hmac as _hmac

    if not signature or not _hmac.compare_digest(hmac_sha256_hex(s.razorpay_webhook_secret, body), signature):
        return PlainTextResponse("invalid signature", status_code=401)
    try:
        evt = json.loads(body)
    except ValueError:
        return PlainTextResponse("bad json", status_code=400)
    sub = ((evt.get("payload") or {}).get("subscription") or {}).get("entity")
    if not str(evt.get("event", "")).startswith("subscription.") or not sub:
        return PlainTextResponse("ignored")
    pay = ((evt.get("payload") or {}).get("payment") or {}).get("entity")
    payment = {"id": pay["id"], "amount": pay["amount"], "method": pay.get("method")} if pay and pay.get("id") and pay.get("status", "captured") == "captured" else None
    apply_subscription(db, evt["event"], {"id": sub["id"], "status": sub["status"], "current_end": sub.get("current_end"), "notes": sub.get("notes")}, payment)
    return PlainTextResponse("ok")
