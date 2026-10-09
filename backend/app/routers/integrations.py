"""Integration keys (stored server-side, never returned) + live connect / sync endpoints."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.deps import Workspace, read_ws, require_ws
from ..core.lib import ADMIN_ROLES, MANAGE_ROLES, PLATFORMS, ApiError, epoch_ms, notify
from ..database import get_db
from ..models import Integration, SocialAccount
from ..services.meta import graph_get
from ..services.sync_service import connect_live, platform_integration, sync_one

router = APIRouter(tags=["integrations"])


def _hint(secret: str | None) -> str | None:
    return f"••••{secret[-4:]}" if secret else None


def _row(db: Session, agency_id: str) -> Integration:
    row = db.scalar(select(Integration).where(Integration.agency_id == agency_id))
    if not row:
        row = Integration(agency_id=agency_id)
        db.add(row)
        db.flush()
    return row


@router.get("/integrations/status")
def status(ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    row = db.scalar(select(Integration).where(Integration.agency_id == ws.agency.id))
    shared = platform_integration(db)
    is_owner = bool(shared and row and shared.id == row.id)
    shared_meta_valid = bool(shared and shared.meta_access_token and shared.ig_business_id
                             and (not shared.meta_token_expires_at or shared.meta_token_expires_at > epoch_ms()))
    return {
        "shared": {"isPlatformOwner": is_owner, "youtube": not is_owner and bool(shared and shared.youtube_api_key),
                   "instagram": not is_owner and shared_meta_valid},
        "youtube": {"configured": bool(row and row.youtube_api_key), "keyHint": _hint(row.youtube_api_key if row else None),
                    "ready": bool((row and row.youtube_api_key) or (shared and shared.youtube_api_key))},
        "meta": {
            "configured": bool(row and row.meta_access_token),
            "tokenHint": _hint(row.meta_access_token if row else None),
            "expiresAt": row.meta_token_expires_at if row else None,
            "appId": row.meta_app_id if row else None,
            "igUsername": row.ig_username if row else None,
            "instagramReady": bool(row and row.ig_business_id) or shared_meta_valid,
            "facebookReady": bool(row and row.meta_access_token),
            "pages": (row.meta_pages if row else None) or [],
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
    """Exchanges a short-lived token for a ~60 day token (when App ID + Secret given) and discovers Instagram + Pages."""
    token = body.token.strip()
    if not token:
        raise ApiError("Access token daalein.")
    expires_at, long_lived = None, False
    app_id, app_secret = (body.appId or "").strip(), (body.appSecret or "").strip()
    if app_id and app_secret:
        ex = graph_get("oauth/access_token", {"grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": app_secret, "fb_exchange_token": token})
        token = ex["access_token"]
        long_lived = True
        expires_at = epoch_ms() + int(ex.get("expires_in") or 60 * 86400) * 1000
    pages = graph_get("me/accounts", {"fields": "id,name,instagram_business_account{id,username}", "limit": "100", "access_token": token}).get("data", [])
    with_ig = next((p for p in pages if p.get("instagram_business_account")), None)
    ig = (with_ig or {}).get("instagram_business_account") or {}
    row = _row(db, ws.agency.id)
    row.meta_access_token, row.meta_token_expires_at, row.meta_app_id = token, expires_at, app_id or None
    row.ig_business_id, row.ig_username = ig.get("id"), ig.get("username")
    row.meta_pages = [p["name"] for p in pages]
    row.updated_at = epoch_ms()
    notify(db, ws.agency.id, "account", f"Meta connect hua{' — Instagram @' + ig['username'] if ig.get('username') else ''}, {len(pages)} Facebook page(s)")
    db.commit()
    return {"igUsername": ig.get("username"), "pages": [p["name"] for p in pages], "longLived": long_lived}


@router.delete("/integrations/meta")
def clear_meta(ws: Workspace = Depends(require_ws(ADMIN_ROLES)), db: Session = Depends(get_db)):
    row = db.scalar(select(Integration).where(Integration.agency_id == ws.agency.id))
    if row:
        row.meta_access_token = row.meta_token_expires_at = row.meta_app_id = row.ig_business_id = row.ig_username = None
        row.meta_pages = None
        db.commit()
    return {"ok": True}


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
