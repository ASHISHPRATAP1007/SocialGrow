"""Live data sync. YouTube + Instagram use the platform owner's keys (shared, so customers need no setup);
Facebook Pages are read ONLY with the agency's own Meta token, so nobody can read pages they don't manage."""
import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.lib import ApiError, epoch_ms, notify, today_iso
from ..models import Integration, Member, MetricDaily, PlatformAdmin, Post, Project, SocialAccount
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


def resolve(db: Session, agency_id: str) -> dict:
    own = db.scalar(select(Integration).where(Integration.agency_id == agency_id))
    shared = platform_integration(db)
    ig = own if own and own.meta_access_token and own.ig_business_id else shared if shared and shared.meta_access_token and shared.ig_business_id else None
    return {
        "youtubeApiKey": (own and own.youtube_api_key) or (shared and shared.youtube_api_key) or None,
        "igToken": ig.meta_access_token if ig else None,
        "igBusinessId": ig.ig_business_id if ig else None,
        "igExpiresAt": ig.meta_token_expires_at if ig else None,
        "ownMetaToken": own.meta_access_token if own else None,
        "ownMetaExpiresAt": own.meta_token_expires_at if own else None,
    }


def fetch_for(platform: str, handle: str, integ: dict) -> dict:
    if platform == "youtube":
        if not integ["youtubeApiKey"]:
            raise ApiError("YouTube live data abhi available nahi hai. Support se contact karein.")
        return fetch_youtube(handle, integ["youtubeApiKey"])
    if platform == "instagram":
        if not integ["igToken"] or not integ["igBusinessId"]:
            raise ApiError("Instagram live data abhi available nahi hai. Support se contact karein.")
        if integ["igExpiresAt"] and integ["igExpiresAt"] < epoch_ms():
            raise ApiError("Instagram connection refresh ho raha hai, thodi der baad try karein.")
        return fetch_instagram(handle, integ["igBusinessId"], integ["igToken"])
    if not integ["ownMetaToken"]:
        raise ApiError("Facebook Page jodne ke liye Settings → Integrations mein apna Meta token connect karein (sirf apne Pages ke liye).")
    if integ["ownMetaExpiresAt"] and integ["ownMetaExpiresAt"] < epoch_ms():
        raise ApiError("Meta token expire ho gaya. Settings mein naya token daalein.")
    return fetch_facebook(handle, integ["ownMetaToken"])


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
