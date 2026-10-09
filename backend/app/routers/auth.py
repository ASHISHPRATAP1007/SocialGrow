import re
import secrets

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..core.deps import get_current_user
from ..core.lib import ApiError, epoch_ms
from ..core.security import create_access_token, hash_code, hash_password, verify_password
from ..database import get_db
from ..models import PasswordReset, User
from ..services.email_service import email_configured, send_email
from ..services.workspace_service import ensure_workspace

router = APIRouter(prefix="/auth", tags=["auth"])
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterIn(BaseModel):
    email: str
    password: str
    agencyName: str | None = None
    phone: str | None = None
    name: str | None = None


class LoginIn(BaseModel):
    email: str
    password: str


class ForgotIn(BaseModel):
    email: str


class ResetIn(BaseModel):
    email: str
    code: str
    newPassword: str


def _token_response(user: User) -> dict:
    return {"accessToken": create_access_token(user.id), "tokenType": "bearer"}


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise ApiError("Valid email daalein.")
    if len(body.password) < 8:
        raise ApiError("Password kam se kam 8 characters ka ho.")
    if db.scalar(select(User).where(User.email == email)):
        raise ApiError("Is email se account pehle se bana hai — sign in karein.")
    user = User(email=email, password_hash=hash_password(body.password), name=(body.name or "").strip() or None, last_login_at=epoch_ms())
    db.add(user)
    db.commit()
    ensure_workspace(db, user, body.agencyName, body.phone)
    return _token_response(user)


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise ApiError("Email ya password galat hai.", 401)
    user.last_login_at = epoch_ms()
    db.commit()
    ensure_workspace(db, user)
    return _token_response(user)


@router.post("/refresh")
def refresh(user: User = Depends(get_current_user)):
    return _token_response(user)


@router.post("/forgot-password")
def forgot_password(body: ForgotIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    # Same response whether or not the account exists (no email enumeration)
    if user:
        if not email_configured():
            raise ApiError("Password reset email abhi set nahi hai. Support se contact karein.")
        code = f"{secrets.randbelow(1_000_000):06d}"
        db.execute(delete(PasswordReset).where(PasswordReset.email == email))
        db.add(PasswordReset(email=email, code_hash=hash_code(code), expires_at=epoch_ms() + 15 * 60_000))
        db.commit()
        send_email(email, "SocialGrow AI — password reset code", f"Aapka password reset code: {code}\n\nYe code 15 minute tak valid hai.")
    return {"ok": True}


@router.post("/reset-password")
def reset_password(body: ResetIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if len(body.newPassword) < 8:
        raise ApiError("Password kam se kam 8 characters ka ho.")
    pr = db.scalar(select(PasswordReset).where(PasswordReset.email == email))
    if not pr or pr.expires_at < epoch_ms() or pr.attempts >= 5:
        raise ApiError("Code expire ho gaya. Dobara 'Password bhool gaye?' karein.")
    if pr.code_hash != hash_code(body.code.strip()):
        pr.attempts += 1
        db.commit()
        raise ApiError("Code galat hai.")
    user = db.scalar(select(User).where(User.email == email))
    if not user:
        raise ApiError("Account nahi mila.")
    user.password_hash = hash_password(body.newPassword)
    db.delete(pr)
    db.commit()
    return _token_response(user)
