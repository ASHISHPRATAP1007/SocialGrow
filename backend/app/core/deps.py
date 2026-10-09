"""FastAPI dependencies: current user, workspace (agency + member), role and subscription checks."""
from dataclasses import dataclass

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Agency, Member, User
from .lib import ApiError, access_for, access_message, is_platform_admin
from .security import decode_access_token


@dataclass
class Workspace:
    user: User
    member: Member
    agency: Agency


def get_current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError("Please sign in again.", 401)
    user_id = decode_access_token(authorization.split(" ", 1)[1])
    user = db.get(User, user_id) if user_id else None
    if not user:
        raise ApiError("Please sign in again.", 401)
    return user


def load_workspace(db: Session, user: User) -> Workspace | None:
    member = db.scalar(select(Member).where(Member.user_id == user.id))
    if not member:
        return None
    agency = db.get(Agency, member.agency_id)
    if not agency:
        return None
    return Workspace(user=user, member=member, agency=agency)


def workspace_or_none(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Workspace | None:
    return load_workspace(db, user)


def require_ws(roles: tuple[str, ...] | None = None, allow_inactive: bool = False):
    """Dependency factory: signed in + in a workspace + allowed role + (unless allow_inactive) subscription active."""

    def dep(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Workspace:
        ws = load_workspace(db, user)
        if not ws:
            raise ApiError("Workspace nahi mila.", 403)
        if roles and ws.member.role not in roles:
            raise ApiError("Aapke role ko ye action karne ki permission nahi hai.", 403)
        if not allow_inactive:
            access = access_for(ws.agency)
            if not access["canWrite"]:
                raise ApiError(access_message(access), 402)
        return ws

    return dep


def read_ws(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Workspace:
    """Read-only access — works even when the subscription expired (data stays visible)."""
    ws = load_workspace(db, user)
    if not ws:
        raise ApiError("Workspace nahi mila.", 403)
    return ws


def require_platform_admin(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    if not is_platform_admin(db, user.id):
        raise ApiError("Admin access required.", 403)
    return user
