"""AI context builder: turns stored analytics into compact JSON snapshots for the model."""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.lib import days_ago, parse_date, pct_change, post_rate, series_for_accounts, summarize, with_post_fallback
from ..models import Client, Post, SocialAccount


def snapshot(db: Session, agency_id: str, start: str, end: str, prev_start: str, prev_end: str,
             client_id: str | None = None, account_id: str | None = None) -> list[dict]:
    accounts = [a for a in db.scalars(select(SocialAccount).where(SocialAccount.agency_id == agency_id)).all()
                if (not client_id or a.client_id == client_id) and (not account_id or a.id == account_id)]
    out = []
    for a in accounts:
        curr = with_post_fallback(db, a, start, end, summarize(series_for_accounts(db, [a.id], start, end)))
        prev = with_post_fallback(db, a, prev_start, prev_end, summarize(series_for_accounts(db, [a.id], prev_start, prev_end)))
        all_posts = db.scalars(select(Post).where(Post.account_id == a.id)).all()
        posts = [p for p in all_posts if start <= p.published_at <= end]
        prev_posts = [p for p in all_posts if prev_start <= p.published_at <= prev_end]
        with_rate = [{"title": p.title, "format": p.format, "date": p.published_at, "views": p.views,
                      "engagementRate": round(post_rate(p, a.followers), 2)} for p in posts]
        by_format: dict[str, dict] = {}
        for p in with_rate:
            f = by_format.setdefault(p["format"], {"posts": 0, "avgEngagement": 0.0, "avgViews": 0.0})
            f["posts"] += 1
            f["avgEngagement"] += p["engagementRate"]
            f["avgViews"] += p["views"]
        for f in by_format.values():
            f["avgEngagement"] = round(f["avgEngagement"] / f["posts"], 2)
            f["avgViews"] = round(f["avgViews"] / f["posts"])
        source = "demo data" if a.mode == "demo" else (
            "platform API (live) — period totals from posts published in the period" if curr["fromPosts"] else "platform API (live)")
        out.append({
            "platform": a.platform,
            "username": a.username,
            "dataSource": source,
            "current": {**curr, "engagementRate": round(curr["engagementRate"], 2), "growthRate": round(curr["growthRate"], 2)},
            "previous": {**prev, "engagementRate": round(prev["engagementRate"], 2)},
            "change": {
                "followersPct": round(pct_change(curr["followers"], prev["followers"]), 2),
                "engagementPct": round(pct_change(curr["engagementRate"], prev["engagementRate"]), 2),
                "viewsPct": round(pct_change(curr["views"], prev["views"]), 2),
            },
            "postsThisPeriod": len(posts),
            "postsPreviousPeriod": len(prev_posts),
            "formatPerformance": by_format,
            "topPosts": sorted(with_rate, key=lambda x: -x["engagementRate"])[:5],
            "weakestPosts": sorted(with_rate, key=lambda x: x["engagementRate"])[:3],
        })
    return out


def analytics_snapshot(db: Session, agency_id: str, days: int, client_id: str | None = None, account_id: str | None = None) -> list[dict]:
    d = max(7, min(180, days))
    return snapshot(db, agency_id, days_ago(d - 1), days_ago(0), days_ago(d * 2 - 1), days_ago(d), client_id, account_id)


def report_data(db: Session, agency_id: str, client_id: str, start: str, end: str) -> dict | None:
    client = db.get(Client, client_id)
    if not client or client.agency_id != agency_id:
        return None
    s, e = parse_date(start), parse_date(end)
    span = max(1, (e - s).days + 1)
    prev_end = (s - timedelta(days=1)).isoformat()
    prev_start = (s - timedelta(days=span)).isoformat()
    return {"client": {"name": client.name, "company": client.company or ""},
            "accounts": snapshot(db, agency_id, start, end, prev_start, prev_end, client_id=client_id)}
