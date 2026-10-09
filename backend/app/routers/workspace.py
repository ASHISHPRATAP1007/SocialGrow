import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.deps import Workspace, get_current_user, load_workspace, read_ws, require_ws
from ..core.lib import ADMIN_ROLES, PLANS, ROLES, ApiError, access_for, is_platform_admin, month_key, notify, require_feature
from ..core.serialize import to_dict
from ..database import get_db
from ..models import AiLog, Member, Notification, User
from ..services.workspace_service import ensure_workspace

router = APIRouter(tags=["workspace"])

AGENCY_PRIVATE = ("razorpay_subscription_id",)


def agency_dict(agency) -> dict:
    return to_dict(agency, exclude=AGENCY_PRIVATE) | {"hasRazorpaySubscription": bool(agency.razorpay_subscription_id)}


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ws = load_workspace(db, user)
    if not ws:
        ensure_workspace(db, user)
        ws = load_workspace(db, user)
    admin = is_platform_admin(db, user.id)
    ai_used = db.scalar(select(func.count()).select_from(AiLog).where(AiLog.agency_id == ws.agency.id, AiLog.month == month_key())) or 0
    unread = db.scalar(select(func.count()).select_from(Notification).where(Notification.agency_id == ws.agency.id, Notification.read.is_(False))) or 0
    return {
        "status": "ready",
        "access": access_for(ws.agency),
        "email": user.email,
        "name": ws.member.name or user.name or user.email.split("@")[0],
        "role": ws.member.role,
        "agency": agency_dict(ws.agency),
        "limits": PLANS[ws.agency.plan],
        "aiUsed": ai_used,
        "unread": unread,
        "isPlatformAdmin": admin,
    }


# ---------------- team ----------------

class InviteIn(BaseModel):
    email: str
    name: str | None = None
    role: str


class RoleIn(BaseModel):
    role: str


@router.get("/members")
def list_members(ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    rows = db.scalars(select(Member).where(Member.agency_id == ws.agency.id).order_by(Member.created_at)).all()
    return [to_dict(m) for m in rows]


@router.post("/members")
def invite_member(body: InviteIn, ws: Workspace = Depends(require_ws(ADMIN_ROLES)), db: Session = Depends(get_db)):
    if body.role not in ROLES or body.role == "owner":
        raise ApiError("Owner role invite nahi kiya ja sakta.")
    email = body.email.strip().lower()
    if "@" not in email:
        raise ApiError("Valid email daalein.")
    members = db.scalars(select(Member).where(Member.agency_id == ws.agency.id)).all()
    limit = PLANS[ws.agency.plan]["members"]
    if len(members) >= limit:
        raise ApiError(f"Aapke plan mein {limit} team member(s) allowed hain. Upgrade karein.")
    if any(m.email == email for m in members):
        raise ApiError("Ye member pehle se team mein hai.")
    if db.scalar(select(Member).where(Member.email == email)):
        raise ApiError("Ye email pehle se kisi aur workspace se juda hai.")
    db.add(Member(agency_id=ws.agency.id, email=email, name=body.name, role=body.role, status="invited"))
    notify(db, ws.agency.id, "team", f"{email} ko {body.role} role ke saath invite kiya gaya")
    db.commit()
    return {"ok": True}


def _member(db: Session, ws: Workspace, member_id: str) -> Member:
    m = db.get(Member, member_id)
    if not m or m.agency_id != ws.agency.id:
        raise ApiError("Member nahi mila.", 404)
    return m


@router.patch("/members/{member_id}")
def update_member_role(member_id: str, body: RoleIn, ws: Workspace = Depends(require_ws(ADMIN_ROLES)), db: Session = Depends(get_db)):
    m = _member(db, ws, member_id)
    if m.role == "owner" or body.role == "owner" or body.role not in ROLES:
        raise ApiError("Owner role badla nahi ja sakta.")
    m.role = body.role
    db.commit()
    return {"ok": True}


@router.delete("/members/{member_id}")
def remove_member(member_id: str, ws: Workspace = Depends(require_ws(ADMIN_ROLES)), db: Session = Depends(get_db)):
    m = _member(db, ws, member_id)
    if m.role == "owner":
        raise ApiError("Owner ko remove nahi kiya ja sakta.")
    db.delete(m)
    db.commit()
    return {"ok": True}


# ---------------- settings / white label ----------------

class SettingsIn(BaseModel):
    name: str
    brandName: str | None = None
    brandColor: str | None = None
    reportFooter: str | None = None
    hideSocialGrowBranding: bool | None = None


@router.put("/settings")
def update_settings(body: SettingsIn, ws: Workspace = Depends(require_ws(ADMIN_ROLES)), db: Session = Depends(get_db)):
    wants_wl = bool(body.brandName or body.reportFooter or body.hideSocialGrowBranding or body.brandColor)
    if wants_wl:
        require_feature(ws.agency, "whiteLabel")
    if body.brandColor and not re.fullmatch(r"#[0-9a-fA-F]{6}", body.brandColor):
        raise ApiError("Color #RRGGBB format mein daalein.")
    a = ws.agency
    a.name = body.name.strip() or a.name
    a.brand_name = (body.brandName or "").strip() or None
    a.brand_color = body.brandColor or None
    a.report_footer = (body.reportFooter or "").strip() or None
    a.hide_social_grow_branding = body.hideSocialGrowBranding
    db.commit()
    return {"ok": True}


# ---------------- notifications ----------------

@router.get("/notifications")
def list_notifications(ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    rows = db.scalars(select(Notification).where(Notification.agency_id == ws.agency.id).order_by(Notification.created_at.desc()).limit(100)).all()
    return [to_dict(n) for n in rows]


@router.post("/notifications/read-all")
def mark_all_read(ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    for n in db.scalars(select(Notification).where(Notification.agency_id == ws.agency.id, Notification.read.is_(False))).all():
        n.read = True
    db.commit()
    return {"ok": True}
