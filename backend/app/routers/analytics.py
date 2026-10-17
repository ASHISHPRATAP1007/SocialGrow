from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.deps import Workspace, read_ws, require_ws
from ..core.lib import CONTENT_ROLES, ApiError, days_ago, pct_change, post_rate, series_for_accounts, summarize, with_post_fallback
from ..core.serialize import to_dict
from ..database import get_db
from ..models import Client, MetricDaily, Post, SocialAccount
from ..config import settings
from ..services.google import UPLOAD_SCOPE, start_upload
from ..services.google import access_token as google_access_token
from ..services.sync_service import resolve

router = APIRouter(tags=["analytics"])


def _combine(stats: list[dict], base: dict) -> dict:
    """Sum counts; average engagement per account so each uses its own basis (views or followers)."""
    total = lambda k: sum(x[k] for x in stats)  # noqa: E731
    active = [x for x in stats if x["views"] + x["likes"] + x["comments"] + x["shares"] > 0]
    return {**base, "views": total("views"), "likes": total("likes"), "comments": total("comments"), "shares": total("shares"),
            "posts": total("posts"), "engagementRate": sum(x["engagementRate"] for x in active) / len(active) if active else 0}


@router.get("/analytics/overview")
def overview(days: int = 30, clientId: str | None = None, projectId: str | None = None, accountId: str | None = None,
             platform: str | None = None, ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    days = max(7, min(365, round(days)))
    accounts = [a for a in db.scalars(select(SocialAccount).where(SocialAccount.agency_id == ws.agency.id)).all()
                if (not clientId or a.client_id == clientId) and (not projectId or a.project_id == projectId)
                and (not accountId or a.id == accountId) and (not platform or a.platform == platform)]
    ids = [a.id for a in accounts]
    start, end = days_ago(days - 1), days_ago(0)
    prev_start, prev_end = days_ago(min(364, days * 2 - 1)), days_ago(days)
    series = series_for_accounts(db, ids, start, end)
    prev_series = series_for_accounts(db, ids, prev_start, prev_end) if days <= 182 else []

    per_account = []
    for a in accounts:
        cur = with_post_fallback(db, a, start, end, summarize(series_for_accounts(db, [a.id], start, end)))
        prev = with_post_fallback(db, a, prev_start, prev_end, summarize(series_for_accounts(db, [a.id], prev_start, prev_end))) if prev_series else None
        per_account.append((a, cur, prev))

    curr = _combine([c for _, c, _ in per_account], summarize(series))
    prev = _combine([p for _, _, p in per_account if p], summarize(prev_series))
    comparable = [(c, p) for _, c, p in per_account if p and not c["fromPosts"] and not p["fromPosts"]]
    cmp_cur = _combine([c for c, _ in comparable], curr)
    cmp_prev = _combine([p for _, p in comparable], prev)

    per_platform = []
    for pl in ("instagram", "facebook", "youtube"):
        mine = [(a, c) for a, c, _ in per_account if a.platform == pl]
        if not mine:
            continue
        base = summarize(series_for_accounts(db, [a.id for a, _ in mine], start, end))
        per_platform.append({"platform": pl, "accounts": len(mine), **_combine([c for _, c in mine], base)})

    chart = [p for i, p in enumerate(series) if i % 7 == 0 or i == len(series) - 1] if days > 90 else series
    quiet = []
    for a in accounts:
        if a.mode != "api":
            continue
        last = db.scalar(select(Post.published_at).where(Post.account_id == a.id).order_by(Post.published_at.desc()).limit(1))
        if not last or last < start:
            quiet.append({"id": a.id, "platform": a.platform, "username": a.username, "lastPostAt": last})
    return {
        "quietAccounts": quiet,
        "days": days,
        "accountCount": len(accounts),
        "hasDemo": any(a.mode == "demo" for a in accounts),
        "hasLive": any(a.mode == "api" for a in accounts),
        "accounts": [{"id": a.id, "platform": a.platform, "username": a.username, "status": a.status, "mode": a.mode} for a in accounts],
        "totals": curr,
        "deltas": {
            "followers": pct_change(curr["followers"], prev["followers"]),
            "engagement": pct_change(cmp_cur["engagementRate"], cmp_prev["engagementRate"]) if comparable else None,
            "views": pct_change(cmp_cur["views"], cmp_prev["views"]) if comparable else None,
            "likes": pct_change(cmp_cur["likes"], cmp_prev["likes"]) if comparable else None,
        } if prev_series else None,
        "perPlatform": per_platform,
        "chart": [{
            "date": p["date"], "followers": p["followers"], "views": p["views"],
            "engagement": round(((p["likes"] + p["comments"] + p["shares"]) / p["views"] * 100) if p["views"]
                                else ((p["likes"] + p["comments"] + p["shares"]) / p["followers"] * 100) if p["followers"] else 0, 2),
        } for p in chart],
    }


@router.get("/posts")
def posts_list(days: int = 90, sort: str = "recent", platform: str | None = None, accountId: str | None = None,
               ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    q = select(Post).where(Post.agency_id == ws.agency.id)
    if days and days > 0:  # 0 = all time
        q = q.where(Post.published_at >= days_ago(days))
    posts = db.scalars(q).all()
    accounts = {a.id: a for a in db.scalars(select(SocialAccount).where(SocialAccount.agency_id == ws.agency.id)).all()}
    avg: dict[str, float] = {}
    for aid, a in accounts.items():
        rates = [post_rate(p, a.followers) / 100 for p in posts if p.account_id == aid]
        avg[aid] = sum(rates) / len(rates) if rates else 0
    rows = []
    for p in posts:
        if (platform and p.platform != platform) or (accountId and p.account_id != accountId):
            continue
        a = accounts.get(p.account_id)
        rate = post_rate(p, a.followers if a else None) / 100
        base = avg.get(p.account_id, 0)
        perf = "average" if base == 0 else "above" if rate > base * 1.1 else "below" if rate < base * 0.9 else "average"
        rows.append(to_dict(p) | {"username": a.username if a else "—", "live": bool(a and a.mode == "api"), "engagementRate": rate * 100, "performance": perf})
    key = {"views": lambda r: -r["views"], "engagement": lambda r: -r["engagementRate"]}.get(sort)
    rows.sort(key=key) if key else rows.sort(key=lambda r: r["publishedAt"], reverse=True)
    return rows[:200]


def _profile_url(a: SocialAccount) -> str | None:
    if a.platform == "youtube":
        return f"https://www.youtube.com/channel/{a.external_id}" if a.external_id else f"https://www.youtube.com/@{a.username}"
    if a.platform == "instagram":
        return f"https://www.instagram.com/{a.username}/"
    return f"https://www.facebook.com/{a.external_id or a.username}"


@router.get("/accounts/{account_id}/details")
def account_details(account_id: str, ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    """Everything about one account — lifetime totals, all stored posts, best posts, monthly and format breakdown.
    No date range, so quiet accounts (no recent posts) still show their full picture."""
    a = db.get(SocialAccount, account_id)
    if not a or a.agency_id != ws.agency.id:
        raise ApiError("Account nahi mila.", 404)
    client = db.get(Client, a.client_id)
    posts = db.scalars(select(Post).where(Post.account_id == a.id).order_by(Post.published_at.desc())).all()
    rows = [to_dict(p) | {"engagementRate": post_rate(p, a.followers)} for p in posts]
    n = len(posts)
    views, likes = sum(p.views for p in posts), sum(p.likes for p in posts)
    comments, shares = sum(p.comments for p in posts), sum(p.shares for p in posts)
    inter = likes + comments + shares
    base = views if views > 0 else (a.followers or 0) * n
    months: dict[str, dict] = {}
    for p in posts:
        m = months.setdefault(p.published_at[:7], {"month": p.published_at[:7], "posts": 0, "views": 0, "likes": 0, "comments": 0})
        m["posts"] += 1
        m["views"] += p.views
        m["likes"] += p.likes
        m["comments"] += p.comments
    formats: dict[str, dict] = {}
    for p in posts:
        f = formats.setdefault(p.format, {"format": p.format, "posts": 0, "views": 0, "rate": 0.0})
        f["posts"] += 1
        f["views"] += p.views
        f["rate"] += post_rate(p, a.followers)
    history = db.scalars(select(MetricDaily).where(MetricDaily.account_id == a.id).order_by(MetricDaily.date)).all()
    gap = None
    if posts:
        from datetime import date
        gap = (date.today() - date.fromisoformat(posts[0].published_at)).days
    return {
        "account": {"id": a.id, "platform": a.platform, "username": a.username, "displayName": a.display_name, "mode": a.mode,
                    "followers": a.followers or 0, "totalViews": a.last_total_views, "status": a.status, "syncError": a.sync_error,
                    "lastSyncedAt": a.last_synced_at, "clientName": client.name if client else None, "url": _profile_url(a)},
        "lifetime": {"posts": n, "views": views, "likes": likes, "comments": comments, "shares": shares,
                     "avgViews": views / n if n else 0, "avgLikes": likes / n if n else 0, "avgComments": comments / n if n else 0,
                     "engagementRate": inter / base * 100 if base else 0,
                     "firstPostAt": posts[-1].published_at if posts else None, "lastPostAt": posts[0].published_at if posts else None,
                     "daysSinceLastPost": gap},
        "bestByViews": sorted(rows, key=lambda r: -r["views"])[:5],
        "bestByEngagement": sorted(rows, key=lambda r: -r["engagementRate"])[:5],
        "monthly": sorted(months.values(), key=lambda m: m["month"])[-12:],
        "formats": [{"format": f["format"], "posts": f["posts"], "avgViews": f["views"] / f["posts"], "avgEngagement": f["rate"] / f["posts"]}
                    for f in formats.values()],
        "history": [{"date": h.date, "followers": h.followers, "views": h.views} for h in history],
        "posts": rows,
        "commentsSupported": a.mode == "api",
    }


# ---------------- upload a video to YouTube ----------------

class UploadIn(BaseModel):
    title: str
    description: str = ""
    tags: list[str] = []
    privacy: str = "private"  # private | unlisted | public
    publishAt: str | None = None  # ISO datetime — schedule (video stays private until then)
    madeForKids: bool = False
    categoryId: str = "22"  # People & Blogs
    size: int
    mimeType: str = "video/mp4"


@router.get("/accounts/{account_id}/youtube/upload-status")
def upload_status(account_id: str, ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    a = db.get(SocialAccount, account_id)
    if not a or a.agency_id != ws.agency.id:
        raise ApiError("Account nahi mila.", 404)
    own = resolve(db, a.agency_id)["googleChannels"].get(a.external_id or "") or {}
    return {"youtube": a.platform == "youtube", "ownChannel": bool(own.get("refreshToken")),
            "canUpload": bool(own.get("refreshToken") and UPLOAD_SCOPE in (own.get("scope") or ""))}


@router.post("/accounts/{account_id}/youtube/upload-session")
def upload_session(account_id: str, body: UploadIn, ws: Workspace = Depends(require_ws(CONTENT_ROLES)), db: Session = Depends(get_db)):
    a = db.get(SocialAccount, account_id)
    if not a or a.agency_id != ws.agency.id or a.platform != "youtube":
        raise ApiError("YouTube account nahi mila.", 404)
    title = body.title.strip()
    if not title or len(title) > 100:
        raise ApiError("Title 1–100 characters ka hona chahiye.")
    if len(body.description) > 5000:
        raise ApiError("Description max 5000 characters.")
    if body.privacy not in ("private", "unlisted", "public"):
        raise ApiError("Privacy galat hai.")
    if body.size <= 0 or body.size > 256 * 1024**3:
        raise ApiError("File size galat hai.")
    if not body.mimeType.startswith("video/"):
        raise ApiError("Sirf video file upload ho sakti hai.")
    integ = resolve(db, a.agency_id)
    own = integ["googleChannels"].get(a.external_id or "") or {}
    if not (own.get("refreshToken") and UPLOAD_SCOPE in (own.get("scope") or "") and integ["googleApp"]):
        raise ApiError("Upload ke liye is channel ko Social Accounts → 'Connect with Google' se dobara jodein (upload permission ke saath).")
    status = {"privacyStatus": body.privacy, "selfDeclaredMadeForKids": body.madeForKids}
    if body.publishAt:
        try:
            when = datetime.fromisoformat(body.publishAt.replace("Z", "+00:00"))
        except ValueError:
            raise ApiError("Schedule time galat hai.") from None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when <= datetime.now(timezone.utc):
            raise ApiError("Schedule time future mein hona chahiye.")
        status = {**status, "privacyStatus": "private", "publishAt": when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    meta = {"snippet": {"title": title, "description": body.description, "tags": [t.strip() for t in body.tags if t.strip()][:30],
                        "categoryId": body.categoryId}, "status": status}
    token = google_access_token(*integ["googleApp"], own["refreshToken"])
    url = start_upload(token, meta, body.size, body.mimeType, settings.FRONTEND_URL.rstrip("/"))
    return {"uploadUrl": url}
