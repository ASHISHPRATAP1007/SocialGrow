"""Integration keys (stored server-side, never returned) + live connect / sync endpoints.

One-time owner setup: YouTube key + Meta App (ID/secret) + owner's Instagram connection.
After that every agency gets YouTube/Instagram automatically and connects Facebook with one click (OAuth).
Meta Page tokens are non-expiring, so nobody has to paste a new token every 60 days."""
import secrets
import time
from collections.abc import Callable
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..core.deps import Workspace, read_ws, require_ws
from ..core.lib import ADMIN_ROLES, DAY, MANAGE_ROLES, PLATFORMS, ApiError, epoch_ms, is_platform_admin, notify
from ..database import get_db
from ..models import Agency, Client, ConnectLink, Integration, Member, PlatformSettings, SocialAccount
from ..services.google import exchange_code as exchange_code_google
from ..services.google import my_channels
from ..services.google import oauth_url as google_oauth_url
from ..services.meta import discover, exchange_code, long_lived, oauth_url
from ..services.sync_service import add_items, available_items, connect_live, ig_valid, platform_integration, sync_one

router = APIRouter(tags=["integrations"])
REDIRECT_PATH = "/api/v1/integrations/meta/callback"
GOOGLE_REDIRECT_PATH = "/api/v1/integrations/google/callback"


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


def _google_app(db: Session) -> tuple[str | None, str | None]:
    s = db.scalar(select(PlatformSettings))
    return (s.google_client_id, s.google_client_secret) if s else (None, None)


def google_redirect_uri() -> str:
    return f"{settings.PUBLIC_API_URL.rstrip('/')}{GOOGLE_REDIRECT_PATH}"


def _store_meta(db: Session, agency_id: str, user_token: str, expires_at: int | None, app_id: str | None,
                keep_user_token: bool = False) -> dict:
    """Saves the Pages (and linked Instagram) this login can see. Merges with earlier logins, so an agency can
    connect its own pages AND each client can connect theirs via a connect link."""
    info = discover(user_token)
    row = _row(db, agency_id)
    if not (keep_user_token and row.meta_access_token):
        row.meta_access_token, row.meta_token_expires_at, row.meta_app_id = user_token, expires_at, app_id
    if not ig_valid(row) or not row.ig_business_id:
        row.ig_business_id, row.ig_username = info["igId"] or row.ig_business_id, info["igUsername"] or row.ig_username
    merged = {**(row.meta_page_tokens or {}), **info["pageTokens"]}
    row.meta_page_tokens = merged
    row.meta_pages = [p["name"] for p in merged.values()]
    row.updated_at = epoch_ms()
    # Accounts that failed on an old token come back automatically
    for acc in db.scalars(select(SocialAccount).where(SocialAccount.agency_id == agency_id, SocialAccount.status == "needs_reconnect")).all():
        acc.status, acc.sync_error = "connected", None
    notify(db, agency_id, "account", f"Facebook connect hua — {len(info['pages'])} page(s)"
           + (f", Instagram @{info['igUsername']}" if info["igUsername"] else ""))
    db.commit()
    return info


def _meta_items(info: dict) -> list[dict]:
    items = []
    for pid, p in info["pageTokens"].items():
        if not p.get("token"):
            continue
        items.append({"platform": "facebook", "id": pid, "name": p["name"], "username": p.get("username")})
        if p.get("igId"):
            items.append({"platform": "instagram", "id": p["igId"], "name": p.get("igUsername") or p["name"], "username": p.get("igUsername")})
    return items


@router.get("/integrations/status")
def status(ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    row = db.scalar(select(Integration).where(Integration.agency_id == ws.agency.id))
    shared = platform_integration(db)
    is_admin = is_platform_admin(db, ws.user.id)
    is_owner = is_admin and (not shared or (row is not None and shared.id == row.id))
    app_id, app_secret = _meta_app(db)
    g_id, g_secret = _google_app(db)
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
        "google": {
            "appConfigured": bool(g_id and g_secret),
            "clientIdHint": _hint(g_id) if is_owner else None,
            "channels": [c["title"] for c in ((row.google_channels if row else None) or {}).values()],
            "redirectUri": google_redirect_uri() if is_owner else None,
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


# ---------------- one-click "Connect with Facebook / Google" (OAuth) ----------------
# The same callbacks serve (a) agency members inside the app and (b) clients opening a connect link
# (no SocialGrow login). With a client chosen, every page / Instagram / channel is added automatically.

BACK_PAGES = ("settings", "social-accounts", "clients")


def make_state(provider: str, agency_id: str, *, user: str | None = None, link: str | None = None,
               client: str | None = None, back: str = "settings") -> str:
    return jwt.encode({"aud": f"{provider}-oauth", "agency": agency_id, "user": user, "link": link, "client": client,
                       "back": back if back in BACK_PAGES else "settings", "exp": int(time.time()) + 900},
                      settings.JWT_SECRET, algorithm="HS256")


def _check_client(db: Session, agency_id: str, client_id: str | None) -> str | None:
    if not client_id:
        return None
    c = db.get(Client, client_id)
    if not c or c.agency_id != agency_id:
        raise ApiError("Client nahi mila.")
    return c.id


def provider_url(db: Session, provider: str, state: str) -> str:
    if provider == "facebook":
        app_id, app_secret = _meta_app(db)
        if not (app_id and app_secret):
            raise ApiError("Facebook connect abhi set nahi hai. Support se contact karein.")
        return oauth_url(app_id, redirect_uri(), state)
    if provider == "google":
        cid, secret = _google_app(db)
        if not (cid and secret):
            raise ApiError("Google (YouTube) connect abhi set nahi hai. Support se contact karein.")
        return google_oauth_url(cid, google_redirect_uri(), state)
    raise ApiError("Provider galat hai.")


@router.get("/integrations/{provider}/connect-url")
def connect_url(provider: str, clientId: str | None = None, back: str = "settings",
                ws: Workspace = Depends(require_ws(MANAGE_ROLES)), db: Session = Depends(get_db)):
    if provider not in ("meta", "facebook", "google"):
        raise ApiError("Provider galat hai.", 404)
    provider = "facebook" if provider == "meta" else provider
    client = _check_client(db, ws.agency.id, clientId)
    return {"url": provider_url(db, provider, make_state(provider, ws.agency.id, user=ws.user.id, client=client, back=back))}


def _finish(db: Session, provider: str, claims: dict | None, run: Callable[[str, bool], list[dict]] | None) -> RedirectResponse:
    """Validates who started the login, runs the token exchange, auto-adds accounts, and redirects back."""
    fe = settings.FRONTEND_URL.rstrip("/")
    if not claims:
        return RedirectResponse(f"{fe}/settings?oauth=error&provider={provider}&reason=session")
    link_token = claims.get("link")
    back = f"{fe}/connect/{link_token}" if link_token else f"{fe}/{claims.get('back') or 'settings'}"

    def go(status: str, **extra) -> RedirectResponse:
        q = urlencode({"oauth": status, "provider": provider, **extra})
        return RedirectResponse(f"{back}?{q}")

    client_id = claims.get("client")
    if link_token:
        link = db.scalar(select(ConnectLink).where(ConnectLink.token == link_token))
        if not link or link.agency_id != claims["agency"] or link.expires_at < epoch_ms():
            return go("error", reason="link")
        client_id = link.client_id
    else:
        member = db.scalar(select(Member).where(Member.user_id == claims.get("user"), Member.agency_id == claims["agency"]))
        if not member or member.role not in MANAGE_ROLES:
            return go("error", reason="permission")
    if run is None:  # user pressed Cancel on the Facebook / Google screen
        return go("cancelled")
    try:
        items = run(claims["agency"], bool(link_token))
    except ApiError as e:
        return go("error", reason=provider, message=str(e.detail)[:150])
    added = 0
    if client_id and items:
        res = add_items(db, claims["agency"], client_id, items)
        added = len(res["added"])
    if link_token:
        link = db.scalar(select(ConnectLink).where(ConnectLink.token == link_token))
        link.uses, link.last_used_at = (link.uses or 0) + 1, epoch_ms()
        notify(db, link.agency_id, "account", f"Client ne connect link se {provider.title()} joda — {added} account(s) add hue")
        db.commit()
    return go("connected", found=len(items), added=added)


def _decode(state: str | None, provider: str) -> dict | None:
    try:
        return jwt.decode(state or "", settings.JWT_SECRET, algorithms=["HS256"], audience=f"{provider}-oauth")
    except jwt.PyJWTError:
        return None


@router.get(REDIRECT_PATH.removeprefix("/api/v1"))
def meta_callback(code: str | None = None, state: str | None = None, error_description: str | None = None, db: Session = Depends(get_db)):
    claims = _decode(state, "facebook")
    if claims and not code:
        return _finish(db, "facebook", claims, None)

    def run(agency_id: str, via_link: bool) -> list[dict]:
        app_id, app_secret = _meta_app(db)
        short = exchange_code(app_id, app_secret, redirect_uri(), code)
        token, expires_at = long_lived(app_id, app_secret, short)
        return _meta_items(_store_meta(db, agency_id, token, expires_at, app_id, keep_user_token=via_link))

    return _finish(db, "facebook", claims, run)


@router.get(GOOGLE_REDIRECT_PATH.removeprefix("/api/v1"))
def google_callback(code: str | None = None, state: str | None = None, error: str | None = None, db: Session = Depends(get_db)):
    claims = _decode(state, "google")
    if claims and not code:
        return _finish(db, "google", claims, None)

    def run(agency_id: str, via_link: bool) -> list[dict]:
        cid, secret = _google_app(db)
        tok = exchange_code_google(cid, secret, google_redirect_uri(), code)
        channels = my_channels(tok["access_token"])
        if not channels:
            raise ApiError("Is Google account mein koi YouTube channel nahi mila.")
        row = _row(db, agency_id)
        merged = dict(row.google_channels or {})
        for c in channels:
            prev = merged.get(c["id"], {})
            merged[c["id"]] = {"title": c["title"], "handle": c["handle"],
                               "refreshToken": tok.get("refresh_token") or prev.get("refreshToken"),
                               "scope": tok.get("scope") or prev.get("scope") or ""}
        row.google_channels = merged
        row.updated_at = epoch_ms()
        for acc in db.scalars(select(SocialAccount).where(SocialAccount.agency_id == agency_id, SocialAccount.platform == "youtube",
                                                          SocialAccount.status == "needs_reconnect")).all():
            if acc.external_id in merged:
                acc.status, acc.sync_error = "connected", None
        notify(db, agency_id, "account", f"Google connect hua — {len(channels)} YouTube channel(s)")
        db.commit()
        return [{"platform": "youtube", "id": c["id"], "name": c["title"], "username": c["handle"]} for c in channels]

    return _finish(db, "google", claims, run)


class GoogleAppIn(BaseModel):
    clientId: str
    clientSecret: str


@router.put("/integrations/google-app")
def save_google_app(body: GoogleAppIn, ws: Workspace = Depends(require_ws(ADMIN_ROLES)), db: Session = Depends(get_db)):
    """One-time owner setup: Google OAuth client for everyone's "Connect with Google"."""
    if not is_platform_admin(db, ws.user.id):
        raise ApiError("Sirf platform owner ye set kar sakta hai.", 403)
    cid, secret = body.clientId.strip(), body.clientSecret.strip()
    if cid and not cid.endswith(".apps.googleusercontent.com"):
        raise ApiError("Ye Client ID nahi hai. Google Cloud → Credentials → OAuth 2.0 Client ID copy karein (…apps.googleusercontent.com par khatam hota hai).")
    if cid and not secret:
        raise ApiError("Client Secret bhi daalein.")
    s = db.scalar(select(PlatformSettings)) or PlatformSettings()
    s.google_client_id, s.google_client_secret = cid or None, secret or None
    s.updated_at = epoch_ms()
    db.add(s)
    db.commit()
    return {"ok": True}


@router.delete("/integrations/google")
def clear_google(ws: Workspace = Depends(require_ws(ADMIN_ROLES)), db: Session = Depends(get_db)):
    row = db.scalar(select(Integration).where(Integration.agency_id == ws.agency.id))
    if row:
        row.google_channels = None
        db.commit()
    return {"ok": True}


# ---------------- connected-but-not-added items ----------------

@router.get("/accounts/available")
def accounts_available(ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    return available_items(db, ws.agency.id)


class AddItem(BaseModel):
    platform: str
    id: str


class AddConnectedIn(BaseModel):
    clientId: str
    items: list[AddItem]


@router.post("/accounts/add-connected")
def add_connected(body: AddConnectedIn, ws: Workspace = Depends(require_ws(MANAGE_ROLES)), db: Session = Depends(get_db)):
    _check_client(db, ws.agency.id, body.clientId)
    avail = {(i["platform"], i["id"]): i for i in available_items(db, ws.agency.id)}
    items = [avail[(i.platform, i.id)] for i in body.items if (i.platform, i.id) in avail]
    if not items:
        raise ApiError("Koi naya account nahi chuna.")
    return add_items(db, ws.agency.id, body.clientId, items)


# ---------------- client connect links (no SocialGrow login needed) ----------------

LINK_DAYS = 30


@router.post("/clients/{client_id}/connect-link")
def create_connect_link(client_id: str, ws: Workspace = Depends(require_ws(MANAGE_ROLES)), db: Session = Depends(get_db)):
    _check_client(db, ws.agency.id, client_id)
    link = db.scalar(select(ConnectLink).where(ConnectLink.client_id == client_id, ConnectLink.expires_at > epoch_ms() + DAY)
                     .order_by(ConnectLink.created_at.desc()))
    if not link:
        link = ConnectLink(token=secrets.token_urlsafe(24), agency_id=ws.agency.id, client_id=client_id,
                           created_by=ws.user.id, expires_at=epoch_ms() + LINK_DAYS * DAY)
        db.add(link)
        db.commit()
    return {"url": f"{settings.FRONTEND_URL.rstrip('/')}/connect/{link.token}", "expiresAt": link.expires_at}


def _link(db: Session, token: str) -> ConnectLink:
    link = db.scalar(select(ConnectLink).where(ConnectLink.token == token))
    if not link or link.expires_at < epoch_ms():
        raise ApiError("Ye link expire ho gaya ya galat hai. Apni agency se naya link maangein.", 404)
    return link


@router.get("/public/connect/{token}")
def public_link_info(token: str, db: Session = Depends(get_db)):
    link = _link(db, token)
    agency, client = db.get(Agency, link.agency_id), db.get(Client, link.client_id)
    fb_id, fb_secret = _meta_app(db)
    g_id, g_secret = _google_app(db)
    accounts = db.scalars(select(SocialAccount).where(SocialAccount.client_id == client.id, SocialAccount.mode == "api")).all()
    return {
        "agencyName": agency.brand_name or agency.name, "brandColor": agency.brand_color, "clientName": client.name,
        "providers": {"facebook": bool(fb_id and fb_secret), "google": bool(g_id and g_secret)},
        "connected": [{"platform": a.platform, "username": a.username} for a in accounts],
    }


@router.get("/public/connect/{token}/start")
def public_link_start(token: str, provider: str, db: Session = Depends(get_db)):
    link = _link(db, token)
    if provider not in ("facebook", "google"):
        raise ApiError("Provider galat hai.")
    return {"url": provider_url(db, provider, make_state(provider, link.agency_id, link=link.token, client=link.client_id))}


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
