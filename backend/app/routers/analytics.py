from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.deps import Workspace, read_ws
from ..core.lib import days_ago, pct_change, post_rate, series_for_accounts, summarize, with_post_fallback
from ..core.serialize import to_dict
from ..database import get_db
from ..models import Post, SocialAccount

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
    return {
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
    posts = db.scalars(select(Post).where(Post.agency_id == ws.agency.id, Post.published_at >= days_ago(days))).all()
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
