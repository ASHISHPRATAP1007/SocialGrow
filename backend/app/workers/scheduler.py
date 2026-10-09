"""Background jobs: live account sync (every 6h) and daily checks (reminders, campaign status, expiry).
Runs inside the API process; on free hosts that sleep, also call POST /api/v1/cron/run from a free cron service."""
import asyncio
import logging
import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.lib import DAY, access_for, days_ago, epoch_ms, notify
from ..database import SessionLocal
from ..models import Agency, Campaign, Integration, SocialAccount
from ..services.sync_service import sync_all

log = logging.getLogger("socialgrow.scheduler")


def daily_checks(db: Session) -> None:
    tomorrow, today = days_ago(-1), days_ago(0)
    for c in db.scalars(select(Campaign)).all():
        if c.end_date == tomorrow and c.status != "completed":
            notify(db, c.agency_id, "campaign", f'Campaign "{c.name}" kal khatam ho raha hai')
        if c.end_date < today and c.status != "completed":
            c.status = "completed"
        if c.start_date <= today <= c.end_date and c.status == "planned":
            c.status = "active"

    for a in db.scalars(select(Agency)).all():
        acc = access_for(a)
        auto = bool(a.razorpay_subscription_id and a.razorpay_sub_status in ("active", "authenticated") and not a.cancel_at_period_end)
        left = acc["daysLeft"]
        if acc["state"] == "trial" and left in (3, 1):
            notify(db, a.id, "billing", f"⏳ Trial {left} din mein khatam — uske baad aapka plan apne aap shuru ho jayega." if auto
                   else f"⏳ Free trial {left} din mein khatam hoga. Kaam chalu rakhne ke liye Billing se subscribe karein.")
        if acc["state"] == "active" and a.subscription_status == "active" and left in (5, 1):
            notify(db, a.id, "billing", f"🔁 {left} din mein auto-renew charge hoga — card/UPI mein balance rakhein." if auto
                   else f"🔔 Plan {left} din mein khatam. Billing page se subscribe karke auto-renew ON karein.")
        if acc["state"] == "grace" and left == 1:
            notify(db, a.id, "billing", "⚠️ Payment pending — kal account read-only ho jayega. Abhi renew karein.")
        if acc["state"] == "expired" and a.subscription_status != "expired" and a.status == "active":
            a.subscription_status = "expired"
            notify(db, a.id, "billing", "🔒 Trial/subscription khatam. Aapka data safe hai — Billing se payment karke turant wapas shuru karein.")

    for i in db.scalars(select(Integration)).all():
        if i.meta_token_expires_at:
            left = math.ceil((i.meta_token_expires_at - epoch_ms()) / DAY)
            if left in (7, 2):
                notify(db, i.agency_id, "account", f"🔑 Meta (Instagram/Facebook) token {left} din mein expire hoga. Settings → Integrations mein naya token daalein.")

    for s in db.scalars(select(SocialAccount).where(SocialAccount.status == "needs_reconnect")).all():
        notify(db, s.agency_id, "account", f"@{s.username} ({s.platform}) ko reconnect karna hoga")
    db.commit()


def run_task(task: str) -> str:
    db = SessionLocal()
    try:
        if task == "sync":
            return f"synced {sync_all(db)} accounts"
        daily_checks(db)
        return "daily checks done"
    finally:
        db.close()


async def scheduler_loop() -> None:
    """Sync every 6 hours; daily checks once a day (~09:00 IST)."""
    last_daily = ""
    last_sync = 0.0
    while True:
        try:
            now = epoch_ms()
            if now - last_sync >= 6 * 3600 * 1000:
                last_sync = now
                await asyncio.to_thread(run_task, "sync")
            today = days_ago(0)
            from datetime import datetime, timezone

            if today != last_daily and datetime.now(timezone.utc).hour >= 3:
                last_daily = today
                await asyncio.to_thread(run_task, "daily")
        except Exception:  # never let the loop die
            log.exception("scheduler job failed")
        await asyncio.sleep(300)
