"""Live data sync. YouTube + Instagram use the platform owner's keys (shared, so customers need no setup);
Facebook Pages are read ONLY with the agency's own Meta token, so nobody can read pages they don't manage."""
import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.lib import ApiError, days_ago, epoch_ms, notify, today_iso
from ..models import Client, Integration, Member, MetricDaily, PlatformAdmin, PlatformSettings, Post, Project, SocialAccount
from .google import access_token as google_access_token
from .meta import fetch_facebook, fetch_instagram
from .youtube import fetch_youtube

log = logging.getLogger("socialgrow.sync")


def platform_integration(db: Session) -> Integration | None:
    for admin in db.scalars(select(PlatformAdmin)).all():
        m = db.scalar(select(Member).where(Member.user_id == admin.user_id))
        if not m:
            continue
        row = db.scalar(select(Integration).where(Integration.agency_id == m.agency_id))
        if row:
            return row
    return None


def ig_credentials(row: Integration | None) -> tuple[str | None, str | None, int | None]:
    """(ig business id, token, expiry). Prefers the non-expiring Page token of the page linked to Instagram."""
    if not row or not row.ig_business_id:
        return None, None, None
    for p in (row.meta_page_tokens or {}).values():
        if p.get("igId") == row.ig_business_id and p.get("token"):
            return row.ig_business_id, p["token"], None
    if row.meta_access_token:
        return row.ig_business_id, row.meta_access_token, row.meta_token_expires_at
    return None, None, None


def ig_valid(row: Integration | None) -> bool:
    ig_id, token, exp = ig_credentials(row)
    return bool(ig_id and token and (not exp or exp > epoch_ms()))


def resolve(db: Session, agency_id: str) -> dict:
    own = db.scalar(select(Integration).where(Integration.agency_id == agency_id))
    shared = platform_integration(db)
    ig_row = own if ig_valid(own) else shared if ig_valid(shared) else None
    ig_id, ig_token, ig_exp = ig_credentials(ig_row)
    page_tokens = (own.meta_page_tokens if own else None) or {}
    ps = db.scalar(select(PlatformSettings))
    return {
        "googleChannels": (own.google_channels if own else None) or {},
        "googleApp": (ps.google_client_id, ps.google_client_secret) if ps and ps.google_client_id and ps.google_client_secret else None,
        "youtubeApiKey": (own and own.youtube_api_key) or (shared and shared.youtube_api_key) or None,
        "igToken": ig_token,
        "igBusinessId": ig_id,
        "igExpiresAt": ig_exp,
        "ownPageTokens": {k: v for k, v in page_tokens.items() if v.get("token")},
    }


def fetch_for(platform: str, handle: str, integ: dict) -> dict:
    if platform == "youtube":
        own = integ.get("googleChannels", {}).get(handle)
        if own and own.get("refreshToken") and integ.get("googleApp"):
            # Channel connected with "Connect with Google" — uses its own login, no API key needed
            return fetch_youtube(handle, "oauth:" + google_access_token(*integ["googleApp"], own["refreshToken"]))
        if not integ["youtubeApiKey"]:
            raise ApiError("YouTube live data abhi available nahi hai. Support se contact karein.")
        return fetch_youtube(handle, integ["youtubeApiKey"])
    if platform == "instagram":
        if not integ["igToken"] or not integ["igBusinessId"]:
            raise ApiError("Instagram live data abhi available nahi hai. Support se contact karein.")
        if integ["igExpiresAt"] and integ["igExpiresAt"] < epoch_ms():
            raise ApiError("Instagram connection refresh ho raha hai, thodi der baad try karein.")
        return fetch_instagram(handle, integ["igBusinessId"], integ["igToken"])
    if not integ["ownPageTokens"]:
        raise ApiError("Facebook Page jodne ke liye Settings → Integrations mein 'Connect with Facebook' dabayein (sirf apne Pages ke liye).")
    return fetch_facebook(handle, integ["ownPageTokens"])


def apply_sync(db: Session, agency_id: str, data: dict, account: SocialAccount | None = None,
               create: tuple[str, str] | None = None) -> SocialAccount:
    """Upserts posts and today's metrics. Daily interactions are deltas since the last sync (first sync = baseline)."""
    if create:
        project_id, platform = create
        project = db.get(Project, project_id)
        if not project or project.agency_id != agency_id:
            raise ApiError("Project nahi mila.")
        dup = db.scalar(select(SocialAccount).where(SocialAccount.agency_id == agency_id, SocialAccount.platform == platform,
                                                    SocialAccount.external_id == data["externalId"]))
        if dup:
            raise ApiError(f"@{data['username']} pehle se connected hai ({'live' if dup.mode == 'api' else 'demo'}).")
        account = SocialAccount(agency_id=agency_id, project_id=project.id, client_id=project.client_id, platform=platform,
                                username=data["username"], external_id=data["externalId"], display_name=data["displayName"],
                                mode="api", status="connected")
        db.add(account)
        db.flush()
        if platform not in (project.platforms or []):
            project.platforms = [*(project.platforms or []), platform]
        notify(db, agency_id, "account", f"@{data['username']} ({platform}) LIVE data ke saath connect hua")
    if not account or account.agency_id != agency_id:
        raise ApiError("Account nahi mila.")
    first_sync = not account.last_synced_at

    d_likes = d_comments = d_shares = d_views = new_posts = 0
    for p in data["posts"]:
        existing = db.scalar(select(Post).where(Post.account_id == account.id, Post.external_id == p["externalId"]))
        if existing:
            d_likes += max(0, p["likes"] - existing.likes)
            d_comments += max(0, p["comments"] - existing.comments)
            d_shares += max(0, p["shares"] - existing.shares)
            d_views += max(0, p["views"] - existing.views)
            existing.title, existing.views, existing.likes = p["title"], p["views"], p["likes"]
            existing.comments, existing.shares, existing.url = p["comments"], p["shares"], p.get("url")
        else:
            db.add(Post(agency_id=agency_id, account_id=account.id, platform=account.platform, format=p["format"], title=p["title"],
                        published_at=p["publishedAt"], external_id=p["externalId"], url=p.get("url"), views=p["views"],
                        likes=p["likes"], comments=p["comments"], shares=p["shares"]))
            if not first_sync:
                new_posts += 1
                d_likes, d_comments, d_shares, d_views = d_likes + p["likes"], d_comments + p["comments"], d_shares + p["shares"], d_views + p["views"]
    total_views = data.get("totalViews")
    if total_views is not None and account.last_total_views is not None:
        d_views = max(0, total_views - account.last_total_views)
    if first_sync:
        d_likes = d_comments = d_shares = d_views = 0

    today = today_iso()
    row = db.scalar(select(MetricDaily).where(MetricDaily.account_id == account.id, MetricDaily.date == today))
    if row:
        row.followers, row.following = data["followers"], data["following"]
        row.views += d_views
        row.likes += d_likes
        row.comments += d_comments
        row.shares += d_shares
        row.posts_count += new_posts
    else:
        db.add(MetricDaily(agency_id=agency_id, account_id=account.id, date=today, followers=data["followers"], following=data["following"],
                           views=d_views, likes=d_likes, comments=d_comments, shares=d_shares, posts_count=new_posts))
    account.username = data["username"]
    account.display_name = data["displayName"]
    account.followers = data["followers"]
    if total_views is not None:
        account.last_total_views = total_views
    account.last_synced_at = epoch_ms()
    account.sync_error = None
    account.status = "connected"
    db.commit()
    return account


def connect_live(db: Session, agency_id: str, project_id: str, platform: str, handle: str) -> dict:
    data = fetch_for(platform, handle, resolve(db, agency_id))
    apply_sync(db, agency_id, data, create=(project_id, platform))
    return {"username": data["username"], "followers": data["followers"], "posts": len(data["posts"])}


def sync_one(db: Session, account: SocialAccount) -> str | None:
    try:
        handle = account.username if account.platform == "instagram" else (account.external_id or account.username)
        data = fetch_for(account.platform, handle, resolve(db, account.agency_id))
        apply_sync(db, account.agency_id, data, account=account)
        return None
    except Exception as e:
        db.rollback()
        msg = e.detail if isinstance(e, ApiError) else str(e)
        token_problem = bool(re.search(r"token|expired|session|OAuth", msg, re.I))
        account = db.get(SocialAccount, account.id)
        if account:
            if token_problem and account.status != "needs_reconnect":
                notify(db, account.agency_id, "account", f"@{account.username} ({account.platform}) ko reconnect karna hoga: {msg[:120]}")
            account.sync_error = msg[:300]
            if token_problem:
                account.status = "needs_reconnect"
            db.commit()
        return msg


def sync_all(db: Session) -> int:
    accounts = db.scalars(select(SocialAccount).where(SocialAccount.mode == "api")).all()
    for acc in accounts:
        err = sync_one(db, acc)
        if err:
            log.warning("sync failed for %s: %s", acc.id, err)
    return len(accounts)


# ---------------- auto-add accounts after "Connect with Facebook / Google" ----------------

def ensure_project(db: Session, agency_id: str, client_id: str) -> Project:
    """Accounts belong to a project; use the client's first active project or create one."""
    client = db.get(Client, client_id)
    if not client or client.agency_id != agency_id:
        raise ApiError("Client nahi mila.")
    project = db.scalar(select(Project).where(Project.client_id == client_id, Project.status == "active").order_by(Project.created_at))
    if not project:
        project = Project(agency_id=agency_id, client_id=client_id, name=f"{client.name} — Social Media", platforms=[],
                          start_date=today_iso(), end_date=days_ago(-365), status="active")
        db.add(project)
        db.flush()
    return project


def available_items(db: Session, agency_id: str) -> list[dict]:
    """Pages / Instagram / YouTube channels the agency has logged in to but not yet added as accounts."""
    row = db.scalar(select(Integration).where(Integration.agency_id == agency_id))
    if not row:
        return []
    existing = {(a.platform, a.external_id) for a in db.scalars(select(SocialAccount).where(SocialAccount.agency_id == agency_id)).all()}
    out = []
    for pid, p in (row.meta_page_tokens or {}).items():
        if not p.get("token"):
            continue
        if ("facebook", pid) not in existing:
            out.append({"platform": "facebook", "id": pid, "name": p["name"], "username": p.get("username")})
        if p.get("igId") and ("instagram", p["igId"]) not in existing:
            out.append({"platform": "instagram", "id": p["igId"], "name": p.get("igUsername") or p["name"], "username": p.get("igUsername")})
    for cid, c in (row.google_channels or {}).items():
        if ("youtube", cid) not in existing:
            out.append({"platform": "youtube", "id": cid, "name": c["title"], "username": c.get("handle")})
    return out


def _handle_for(item: dict) -> str:
    return item["username"] if item["platform"] == "instagram" else item["id"]


def add_items(db: Session, agency_id: str, client_id: str, items: list[dict]) -> dict:
    """Adds the given connected items as LIVE accounts under the client (first sync included).
    Already-added accounts are skipped (and revived if they needed a reconnect)."""
    project = ensure_project(db, agency_id, client_id)
    project_id = project.id
    db.commit()
    added, errors = [], []
    for it in items:
        dup = db.scalar(select(SocialAccount).where(SocialAccount.agency_id == agency_id, SocialAccount.platform == it["platform"],
                                                    SocialAccount.external_id == it["id"]))
        if dup:
            if dup.status == "needs_reconnect":
                dup.status, dup.sync_error = "connected", None
                db.commit()
            continue
        try:
            if it["platform"] == "instagram" and not it.get("username"):
                raise ApiError("Instagram username nahi mila.")
            data = fetch_for(it["platform"], _handle_for(it), resolve(db, agency_id))
            apply_sync(db, agency_id, data, create=(project_id, it["platform"]))
            added.append({"platform": it["platform"], "username": data["username"]})
        except Exception as e:  # one failing page must not block the rest
            db.rollback()
            errors.append({"platform": it["platform"], "name": it["name"], "error": e.detail if isinstance(e, ApiError) else str(e)})
    return {"added": added, "errors": errors}
