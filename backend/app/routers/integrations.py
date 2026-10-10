"""Integration keys (stored server-side, never returned) + live connect / sync endpoints.

One-time owner setup: YouTube key + Meta App (ID/secret) + owner's Instagram connection.
After that every agency gets YouTube/Instagram automatically and connects Facebook with one click (OAuth).
Meta Page tokens are non-expiring, so nobody has to paste a new token every 60 days."""
import time

import jwt
from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..core.deps import Workspace, read_ws, require_ws
from ..core.lib import ADMIN_ROLES, MANAGE_ROLES, PLATFORMS, ApiError, epoch_ms, is_platform_admin, notify
from ..database import get_db
from ..models import Integration, Member, PlatformSettings, SocialAccount
from ..services.meta import discover, exchange_code, long_lived, oauth_url
from ..services.sync_service import connect_live, ig_valid, platform_integration, sync_one

router = APIRouter(tags=["integrations"])
REDIRECT_PATH = "/api/v1/integrations/meta/callback"


def redirect_uri() -> str:
    return f"{settings.PUBLIC_API_URL.rstrip('/')}{REDIRECT_PATH}"


def _hint(secret: str | None) -> str | None:
    return f"••••{secret[-4:]}" if secret else None


def _row(db: Session, agency_id: str) -> Integration:
    row = db.scalar(select(Integration).where(Integration.agency_id == agency_id))
    if not row:
        row = Integration(agency_id=agency_id)
        db.add(row)
        db.flush()
    return row


def _meta_app(db: Session) -> tuple[str | None, str | None]:
    s = db.scalar(select(PlatformSettings))
    return (s.meta_app_id, s.meta_app_secret) if s else (None, None)


def _store_meta(db: Session, agency_id: str, user_token: str, expires_at: int | None, app_id: str | None) -> dict:
    info = discover(user_token)
    row = _row(db, agency_id)
    row.meta_access_token, row.meta_token_expires_at, row.meta_app_id = user_token, expires_at, app_id
    row.ig_business_id, row.ig_username = info["igId"], info["igUsername"]
    row.meta_pages, row.meta_page_tokens = info["pages"], info["pageTokens"]
    row.updated_at = epoch_ms()
    # Accounts that failed on an old token come back automatically
    for acc in db.scalars(select(SocialAccount).where(SocialAccount.agency_id == agency_id, SocialAccount.status == "needs_reconnect")).all():
        acc.status, acc.sync_error = "connected", None
    notify(db, agency_id, "account", f"Meta connect hua{' — Instagram @' + info['igUsername'] if info['igUsername'] else ''}, {len(info['pages'])} Facebook page(s)")
    db.commit()
    return info


@router.get("/integrations/status")
def status(ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    row = db.scalar(select(Integration).where(Integration.agency_id == ws.agency.id))
    shared = platform_integration(db)
    is_admin = is_platform_admin(db, ws.user.id)
    is_owner = is_admin and (not shared or (row is not None and shared.id == row.id))
    app_id, app_secret = _meta_app(db)
    has_page_tokens = bool(row and any(p.get("token") for p in (row.meta_page_tokens or {}).values()))
    return {
        "shared": {"isPlatformOwner": is_owner, "youtube": not is_owner and bool(shared and shared.youtube_api_key),
                   "instagram": not is_owner and ig_valid(shared)},
        "youtube": {"configured": bool(row and row.youtube_api_key), "keyHint": _hint(row.youtube_api_key if row else None),
                    "ready": bool((row and row.youtube_api_key) or (shared and shared.youtube_api_key))},
        "meta": {
            "configured": bool(row and row.meta_access_token),
            "tokenHint": _hint(row.meta_access_token if row else None),
            "neverExpires": has_page_tokens,
            "expiresAt": None if has_page_tokens else (row.meta_token_expires_at if row else None),
            "igUsername": row.ig_username if row else None,
            "instagramReady": ig_valid(row) or ig_valid(shared),
            "facebookReady": has_page_tokens,
            "pages": (row.meta_pages if row else None) or [],
            "oauthAvailable": bool(app_id and app_secret),
            "appConfigured": bool(app_id and app_secret),
            "redirectUri": redirect_uri() if is_owner else None,
        },
    }


class YoutubeKeyIn(BaseModel):
    apiKey: str


@router.put("/integrations/youtube")
def save_youtube_key(body: YoutubeKeyIn, ws: Workspace = Depends(require_ws(ADMIN_ROLES)), db: Session = Depends(get_db)):
    row = _row(db, ws.agency.id)
    row.youtube_api_key = body.apiKey.strip() or None
    row.updated_at = epoch_ms()
    db.commit()
    return {"ok": True}


class MetaIn(BaseModel):
    token: str
    appId: str | None = None
    appSecret: str | None = None


@router.post("/integrations/meta")
def save_meta(body: MetaIn, ws: Workspace = Depends(require_ws(ADMIN_ROLES)), db: Session = Depends(get_db)):
    """Manual token (owner's first setup / advanced). Exchanges for a long-lived token and stores non-expiring Page tokens.
    When the platform owner gives App ID + Secret they are saved once for everyone's one-click Facebook connect."""
    token = body.token.strip()
    if not token:
        raise ApiError("Access token daalein.")
    app_id, app_secret = (body.appId or "").strip(), (body.appSecret or "").strip()
    if not (app_id and app_secret):
        app_id, app_secret = _meta_app(db)
        app_id, app_secret = app_id or "", app_secret or ""
    expires_at, is_long = None, False
    if app_id and app_secret:
        token, expires_at = long_lived(app_id, app_secret, token)
        is_long = True
        if is_platform_admin(db, ws.user.id) and body.appId and body.appSecret:
            s = db.scalar(select(PlatformSettings)) or PlatformSettings()
            s.meta_app_id, s.meta_app_secret, s.updated_at = app_id, app_secret, epoch_ms()
            db.add(s)
    info = _store_meta(db, ws.agency.id, token, expires_at, app_id or None)
    return {"igUsername": info["igUsername"], "pages": info["pages"], "longLived": is_long,
            "neverExpires": is_long and any(p.get("token") for p in info["pageTokens"].values())}


@router.delete("/integrations/meta")
def clear_meta(ws: Workspace = Depends(require_ws(ADMIN_ROLES)), db: Session = Depends(get_db)):
    row = db.scalar(select(Integration).where(Integration.agency_id == ws.agency.id))
    if row:
        row.meta_access_token = row.meta_token_expires_at = row.meta_app_id = row.ig_business_id = row.ig_username = None
        row.meta_pages = row.meta_page_tokens = None
        db.commit()
    return {"ok": True}


# ---------------- one-click "Connect with Facebook" (OAuth) ----------------

def _state(ws: Workspace) -> str:
    return jwt.encode({"aud": "meta-oauth", "agency": ws.agency.id, "user": ws.user.id, "exp": int(time.time()) + 900},
                      settings.JWT_SECRET, algorithm="HS256")


@router.get("/integrations/meta/connect-url")
def meta_connect_url(ws: Workspace = Depends(require_ws(ADMIN_ROLES)), db: Session = Depends(get_db)):
    app_id, app_secret = _meta_app(db)
    if not (app_id and app_secret):
        raise ApiError("Facebook connect abhi set nahi hai. Support se contact karein.")
    return {"url": oauth_url(app_id, redirect_uri(), _state(ws))}


@router.get(REDIRECT_PATH.removeprefix("/api/v1"))
def meta_callback(code: str | None = None, state: str | None = None, error_description: str | None = None, db: Session = Depends(get_db)):
    back = f"{settings.FRONTEND_URL.rstrip('/')}/settings"
    try:
        claims = jwt.decode(state or "", settings.JWT_SECRET, algorithms=["HS256"], audience="meta-oauth")
    except jwt.PyJWTError:
        return RedirectResponse(f"{back}?meta=error&reason=session")
    if not code:
        return RedirectResponse(f"{back}?meta=cancelled")
    member = db.scalar(select(Member).where(Member.user_id == claims["user"], Member.agency_id == claims["agency"]))
    if not member or member.role not in ADMIN_ROLES:
        return RedirectResponse(f"{back}?meta=error&reason=permission")
    app_id, app_secret = _meta_app(db)
    try:
        short = exchange_code(app_id, app_secret, redirect_uri(), code)
        token, expires_at = long_lived(app_id, app_secret, short)
        _store_meta(db, claims["agency"], token, expires_at, app_id)
    except ApiError:
        return RedirectResponse(f"{back}?meta=error&reason=meta")
    return RedirectResponse(f"{back}?meta=connected")


# ---------------- live accounts ----------------

class LiveIn(BaseModel):
    projectId: str
    platform: str
    handle: str


@router.post("/accounts/live")
def connect_live_account(body: LiveIn, ws: Workspace = Depends(require_ws(MANAGE_ROLES)), db: Session = Depends(get_db)):
    if body.platform not in PLATFORMS:
        raise ApiError("Platform galat hai.")
    if not body.handle.strip():
        raise ApiError("Username / handle daalein.")
    return connect_live(db, ws.agency.id, body.projectId, body.platform, body.handle)


@router.post("/accounts/{account_id}/sync")
def sync_now(account_id: str, ws: Workspace = Depends(require_ws(MANAGE_ROLES)), db: Session = Depends(get_db)):
    acc = db.get(SocialAccount, account_id)
    if not acc or acc.agency_id != ws.agency.id:
        raise ApiError("Account nahi mila.", 404)
    if acc.mode != "api":
        raise ApiError("Demo account sync nahi hota.")
    return {"error": sync_one(db, acc)}
