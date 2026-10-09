from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.lib import DAY, epoch_ms, notify, notify_admins
from ..models import Agency, Member, PlatformAdmin, PlatformSettings, User


def ensure_workspace(db: Session, user: User, agency_name: str | None = None, phone: str | None = None) -> str:
    """Gives a user a workspace: accept a pending team invite, else create a new agency with an automatic free trial.
    The very first user of a fresh install becomes the platform owner (admin) with full access."""
    existing = db.scalar(select(Member).where(Member.user_id == user.id))
    if existing:
        return existing.agency_id
    email = user.email.lower()

    invite = db.scalar(select(Member).where(Member.email == email, Member.status == "invited"))
    if invite:
        invite.user_id = user.id
        invite.status = "active"
        notify(db, invite.agency_id, "team", f"{email} ne team join kar li")
        db.commit()
        return invite.agency_id

    name = (agency_name or "").strip() or f"{email.split('@')[0] or 'My'} Agency"
    first_user = db.scalar(select(PlatformAdmin)) is None

    if first_user:
        agency = Agency(name=name, owner_id=user.id, plan="agency", status="active", phone=(phone or "").strip() or None)
        db.add(agency)
        db.flush()
        db.add(PlatformAdmin(user_id=user.id))
        db.add(Member(agency_id=agency.id, user_id=user.id, email=email, name=user.name, role="owner", status="active"))
        notify(db, agency.id, "welcome", "👑 Aap platform owner hain — Admin Panel se payments, agencies aur integrations manage karein.")
        db.commit()
        return agency.id

    settings_row = db.scalar(select(PlatformSettings))
    trial_days = (settings_row.trial_days if settings_row and settings_row.trial_days else 30)
    agency = Agency(
        name=name,
        owner_id=user.id,
        plan="pro",
        status="active",
        subscription_status="trialing",
        trial_ends_at=epoch_ms() + trial_days * DAY,
        phone=(phone or "").strip() or None,
    )
    db.add(agency)
    db.flush()
    db.add(Member(agency_id=agency.id, user_id=user.id, email=email, name=user.name, role="owner", status="active"))
    notify(db, agency.id, "welcome", f"🎉 Swagat hai! Aapka {trial_days} din ka FREE Pro trial shuru ho gaya. Client → Project banayein aur social accounts connect karein.")
    notify_admins(db, f"Naya signup: {name} ({email}{', ' + phone if phone else ''}) — trial shuru")
    db.commit()
    return agency.id
