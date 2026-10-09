"""Platform owner panel: business stats, agencies, payments verification, trial/UPI settings, Razorpay keys."""
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..core.deps import require_platform_admin
from ..core.lib import DAY, PLAN_KEYS, PLANS, ApiError, access_for, epoch_ms, month_key, notify
from ..core.serialize import to_dict
from ..database import get_db
from ..models import AiLog, Agency, Client, Member, Payment, PlatformSettings, Project, SocialAccount, User
from ..services.razorpay_service import rzp, settings_row

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_platform_admin)])


@router.get("/stats")
def admin_stats(db: Session = Depends(get_db)):
    now = epoch_ms()
    users = db.scalars(select(User)).all()
    agencies = db.scalars(select(Agency)).all()
    members = db.scalars(select(Member)).all()
    clients = db.scalars(select(Client)).all()
    projects_count = len(db.scalars(select(Project.id)).all())
    accounts = db.scalars(select(SocialAccount)).all()
    ai = db.scalars(select(AiLog).where(AiLog.month == month_key())).all()
    payments = db.scalars(select(Payment).order_by(Payment.created_at.desc()).limit(200)).all()
    s = db.scalar(select(PlatformSettings))
    with_access = [(a, access_for(a, now)) for a in agencies]
    paying = [(a, x) for a, x in with_access if x["state"] in ("active", "grace") and a.subscription_status == "active"]
    owner_of = {m.agency_id: m.email for m in members if m.role == "owner"}
    names = {a.id: a.name for a in agencies}
    month_start = int(datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    return {
        "settings": {"upiId": (s.upi_id if s else "") or "", "payeeName": (s.payee_name if s else "") or "",
                     "supportPhone": (s.support_phone if s else "") or "", "trialDays": (s.trial_days if s else None) or 30},
        "totals": {
            "users": len(users),
            "activeUsers": sum(1 for u in users if u.last_login_at and u.last_login_at > now - 30 * DAY),
            "agencies": len(agencies),
            "pending": sum(1 for _, x in with_access if x["state"] == "pending"),
            "trials": sum(1 for _, x in with_access if x["state"] == "trial"),
            "paidAgencies": len(paying),
            "expired": sum(1 for _, x in with_access if x["state"] == "expired"),
            "mrr": sum(round(PLANS[a.plan]["yearlyPrice"] / 12) if a.billing_cycle == "yearly" else PLANS[a.plan]["price"] for a, _ in paying),
            "revenueThisMonth": sum(p.amount for p in payments if p.status == "paid" and p.created_at >= month_start),
            "clients": len(clients),
            "projects": projects_count,
            "accounts": len(accounts),
            "aiRequests": len(ai),
        },
        "planMix": [{"plan": PLANS[p]["label"], "count": sum(1 for a, _ in paying if a.plan == p)} for p in ("starter", "pro", "agency")],
        "pendingAgencies": [{"id": a.id, "name": a.name, "owner": owner_of.get(a.id, "—"), "phone": a.phone or "", "createdAt": a.created_at}
                            for a, x in sorted(with_access, key=lambda t: -t[0].created_at) if x["state"] == "pending"],
        "pendingPayments": [to_dict(p) | {"agency": names.get(p.agency_id, "—"), "owner": owner_of.get(p.agency_id, "—")}
                            for p in payments if p.status == "pending"],
        "agencies": [{
            "id": a.id, "name": a.name, "plan": a.plan, "createdAt": a.created_at, "access": x, "owner": owner_of.get(a.id, "—"),
            "phone": a.phone or "", "billingCycle": a.billing_cycle,
            "autoRenew": bool(a.razorpay_subscription_id and a.razorpay_sub_status in ("active", "authenticated") and not a.cancel_at_period_end),
            "members": sum(1 for m in members if m.agency_id == a.id),
            "clients": sum(1 for c in clients if c.agency_id == a.id),
            "accounts": sum(1 for c in accounts if c.agency_id == a.id),
            "aiThisMonth": sum(1 for l in ai if l.agency_id == a.id),
        } for a, x in sorted(with_access, key=lambda t: -t[0].created_at)[:200]],
        "payments": [to_dict(p) | {"agency": names.get(p.agency_id, "—")} for p in payments if p.status != "pending"][:30],
    }


def _agency(db: Session, agency_id: str) -> Agency:
    a = db.get(Agency, agency_id)
    if not a:
        raise ApiError("Agency nahi mili.", 404)
    return a


@router.post("/agencies/{agency_id}/approve")
def approve(agency_id: str, db: Session = Depends(get_db)):
    a = _agency(db, agency_id)
    s = db.scalar(select(PlatformSettings))
    days = (s.trial_days if s else None) or 30
    a.status, a.plan, a.subscription_status = "active", "pro", "trialing"
    a.trial_ends_at, a.approved_at = epoch_ms() + days * DAY, epoch_ms()
    notify(db, a.id, "billing", f"🎉 Aapka account approve ho gaya! {days} din ka free Pro trial shuru.")
    db.commit()
    return {"ok": True}


@router.post("/agencies/{agency_id}/reject")
def reject(agency_id: str, db: Session = Depends(get_db)):
    _agency(db, agency_id).status = "rejected"
    db.commit()
    return {"ok": True}


class StatusIn(BaseModel):
    status: str


@router.post("/agencies/{agency_id}/status")
def set_status(agency_id: str, body: StatusIn, db: Session = Depends(get_db)):
    if body.status not in ("active", "suspended"):
        raise ApiError("Status galat hai.")
    _agency(db, agency_id).status = body.status
    db.commit()
    return {"ok": True}


class ExtendIn(BaseModel):
    days: int


@router.post("/agencies/{agency_id}/extend")
def extend(agency_id: str, body: ExtendIn, db: Session = Depends(get_db)):
    a = _agency(db, agency_id)
    add, now = round(body.days) * DAY, epoch_ms()
    if not add:
        return {"ok": True}
    if a.subscription_status == "active":
        a.current_period_end = max(now, a.current_period_end or now) + add
    else:
        a.status, a.subscription_status = "active", "trialing"
        a.trial_ends_at = max(now, a.trial_ends_at or now) + add
    notify(db, a.id, "billing", f"Aapke account mein {round(body.days)} din add kiye gaye")
    db.commit()
    return {"ok": True}


class PlanIn(BaseModel):
    plan: str


@router.post("/agencies/{agency_id}/plan")
def set_plan(agency_id: str, body: PlanIn, db: Session = Depends(get_db)):
    if body.plan not in PLAN_KEYS:
        raise ApiError("Plan galat hai.")
    a = _agency(db, agency_id)
    a.plan = body.plan
    notify(db, a.id, "billing", f"Plan {PLANS[body.plan]['label']} set kiya gaya")
    db.commit()
    return {"ok": True}


@router.post("/payments/{payment_id}/verify")
def verify_payment(payment_id: str, db: Session = Depends(get_db)):
    p = db.get(Payment, payment_id)
    if not p or p.status != "pending":
        raise ApiError("Payment pending nahi hai.")
    a = _agency(db, p.agency_id)
    now = epoch_ms()
    base = max(now, (a.current_period_end or now) if a.subscription_status == "active" else now)
    end = base + (p.months or 1) * 30 * DAY
    p.status, p.reviewed_at = "paid", now
    a.status, a.plan, a.subscription_status, a.current_period_end, a.plan_renews_at = "active", p.plan, "active", end, end
    notify(db, a.id, "billing", f"✅ Payment ₹{p.amount:,} verify ho gaya. {PLANS[p.plan]['label']} plan {datetime.fromtimestamp(end / 1000).strftime('%d/%m/%Y')} tak active.")
    db.commit()
    return {"ok": True}


class RejectIn(BaseModel):
    note: str | None = None


@router.post("/payments/{payment_id}/reject")
def reject_payment(payment_id: str, body: RejectIn, db: Session = Depends(get_db)):
    p = db.get(Payment, payment_id)
    if not p or p.status != "pending":
        raise ApiError("Payment pending nahi hai.")
    p.status, p.reviewed_at, p.note = "rejected", epoch_ms(), body.note
    notify(db, p.agency_id, "billing", f"❌ Payment (UTR {p.reference}) verify nahi ho paya{': ' + body.note if body.note else ''}. Sahi UTR ke saath dobara submit karein.")
    db.commit()
    return {"ok": True}


class SettingsIn(BaseModel):
    upiId: str = ""
    payeeName: str = ""
    supportPhone: str = ""
    trialDays: int = 30


@router.put("/settings")
def save_settings(body: SettingsIn, db: Session = Depends(get_db)):
    upi = body.upiId.strip()
    if upi and not re.fullmatch(r"[\w.\-]{2,256}@[a-zA-Z]{2,64}", upi):
        raise ApiError("UPI ID sahi format mein daalein (jaise name@okhdfcbank).")
    s = settings_row(db)
    s.upi_id, s.payee_name, s.support_phone = upi or None, body.payeeName.strip() or None, body.supportPhone.strip() or None
    s.trial_days = max(1, min(90, round(body.trialDays) or 30))
    s.updated_at = epoch_ms()
    db.commit()
    return {"ok": True}


@router.get("/gateway")
def gateway_status(db: Session = Depends(get_db)):
    s = db.scalar(select(PlatformSettings))
    key_id = s.razorpay_key_id if s else None
    return {"keyId": key_id, "mode": ("live" if key_id.startswith("rzp_live_") else "test") if key_id else None,
            "hasWebhookSecret": bool(s and s.razorpay_webhook_secret),
            "webhookUrl": f"{settings.PUBLIC_API_URL.rstrip('/')}/api/v1/webhooks/razorpay",
            "plansCreated": len((s.razorpay_plans if s else None) or {})}


class GatewayIn(BaseModel):
    keyId: str
    keySecret: str
    webhookSecret: str = ""


@router.put("/gateway")
def save_gateway(body: GatewayIn, db: Session = Depends(get_db)):
    key_id, key_secret = body.keyId.strip(), body.keySecret.strip()
    if not re.fullmatch(r"rzp_(test|live)_\w+", key_id):
        raise ApiError("Key ID 'rzp_test_…' ya 'rzp_live_…' jaisa hona chahiye.")
    if not key_secret:
        raise ApiError("Key Secret daalein.")
    rzp(key_id, key_secret, "GET", "/plans?count=1")  # validates the keys
    s = settings_row(db)
    if s.razorpay_key_id != key_id:
        s.razorpay_plans = {}  # plan ids belong to one Razorpay account/mode
    s.razorpay_key_id, s.razorpay_key_secret = key_id, key_secret
    if body.webhookSecret.strip():
        s.razorpay_webhook_secret = body.webhookSecret.strip()
    s.updated_at = epoch_ms()
    db.commit()
    return {"mode": "live" if key_id.startswith("rzp_live_") else "test"}
