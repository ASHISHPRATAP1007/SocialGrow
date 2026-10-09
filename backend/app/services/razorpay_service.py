"""Razorpay subscriptions: plans, subscribe, webhook application (auto-renew)."""
import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.lib import PLANS, ApiError, month_key, notify, notify_admins
from ..models import Agency, Payment, PlatformSettings

API = "https://api.razorpay.com/v1"


def settings_row(db: Session) -> PlatformSettings:
    row = db.scalar(select(PlatformSettings))
    if not row:
        row = PlatformSettings()
        db.add(row)
        db.flush()
    return row


def rzp(key_id: str, key_secret: str, method: str, path: str, body: dict | None = None) -> dict:
    r = httpx.request(method, f"{API}{path}", auth=(key_id, key_secret), json=body, timeout=30)
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code >= 400 or data.get("error"):
        raise ApiError(f"Razorpay: {(data.get('error') or {}).get('description', r.reason_phrase)}")
    return data


def ensure_plan_id(db: Session, s: PlatformSettings, plan: str, cycle: str) -> str:
    key = f"{plan}_{cycle}"
    known = dict(s.razorpay_plans or {})
    if known.get(key):
        return known[key]
    p = PLANS[plan]
    amount = (p["yearlyPrice"] if cycle == "yearly" else p["price"]) * 100
    created = rzp(s.razorpay_key_id, s.razorpay_key_secret, "POST", "/plans", {
        "period": cycle, "interval": 1,
        "item": {"name": f"SocialGrow {p['label']} ({cycle})", "amount": amount, "currency": "INR", "description": f"SocialGrow AI {p['label']} plan"},
        "notes": {"plan": plan, "cycle": cycle},
    })
    known[key] = created["id"]
    s.razorpay_plans = known
    db.commit()
    return created["id"]


def invoice_no(db: Session, agency_id: str) -> str:
    count = db.scalar(select(func.count()).select_from(Payment).where(Payment.agency_id == agency_id)) or 0
    return f"SG-{month_key().replace('-', '')}-{count + 1:04d}"


def apply_subscription(db: Session, event: str, sub: dict, payment: dict | None = None) -> str:
    """Idempotent: payments de-duplicated by Razorpay payment id."""
    agency = db.scalar(select(Agency).where(Agency.razorpay_subscription_id == sub["id"]))
    notes = sub.get("notes") or {}
    if isinstance(notes, list):
        notes = {}
    if not agency and notes.get("agencyId"):
        agency = db.get(Agency, notes["agencyId"])
    if not agency:
        return "agency-not-found"
    plan = notes.get("plan") or agency.plan
    if plan not in PLANS:
        plan = agency.plan
    cycle = notes.get("cycle") or agency.billing_cycle or "monthly"
    period_end = sub["current_end"] * 1000 if sub.get("current_end") else None
    agency.razorpay_subscription_id = sub["id"]
    agency.razorpay_sub_status = sub["status"]

    if payment:
        exists = db.scalar(select(Payment).where(Payment.razorpay_payment_id == payment["id"]))
        if not exists:
            amount = round(payment["amount"] / 100)
            db.add(Payment(agency_id=agency.id, plan=plan, amount=amount, currency="INR", status="paid",
                           method=f"Razorpay ({payment['method']})" if payment.get("method") else "Razorpay",
                           reference=payment["id"], razorpay_payment_id=payment["id"], months=12 if cycle == "yearly" else 1,
                           invoice_no=invoice_no(db, agency.id)))
            notify(db, agency.id, "billing", f"✅ Payment ₹{amount:,} mila — {PLANS[plan]['label']} plan renew ho gaya.")
            notify_admins(db, f"💰 {agency.name}: ₹{amount:,} ({PLANS[plan]['label']}, {cycle})")

    st = sub["status"]
    if st == "active" or event == "subscription.charged":
        if period_end:
            agency.status, agency.plan, agency.billing_cycle = "active", plan, cycle
            agency.subscription_status, agency.current_period_end, agency.plan_renews_at = "active", period_end, period_end
            agency.pending_plan = None
        else:
            agency.billing_cycle, agency.pending_plan = cycle, f"{plan}:{cycle}"
        if event == "subscription.activated":
            notify(db, agency.id, "billing", f"🔁 Auto-renew ON — {PLANS[plan]['label']} ({cycle}). Har cycle pe apne aap charge hoga.")
    elif st == "authenticated":
        agency.billing_cycle, agency.pending_plan = cycle, f"{plan}:{cycle}"
        notify(db, agency.id, "billing", f"🔁 Auto-pay setup ho gaya — {PLANS[plan]['label']}. Pehla charge trial khatam hone par hoga.")
    elif st == "pending":
        notify(db, agency.id, "billing", "⚠️ Renewal payment fail hua. Razorpay dobara try karega — card/UPI balance check karein.")
    elif st == "halted":
        notify(db, agency.id, "billing", "🔴 Renewal payments baar-baar fail hue. Billing page se dobara subscribe karein, warna account read-only ho jayega.")
    elif st in ("cancelled", "completed", "expired"):
        agency.cancel_at_period_end, agency.pending_plan = True, None
        if event != "sync":
            notify(db, agency.id, "billing", "Auto-renew band hua. Plan current period end tak chalega.")
    db.commit()
    return "ok"
