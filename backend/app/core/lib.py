"""Shared business rules: plans, roles, subscription access, notifications, analytics, demo data."""
from __future__ import annotations

import math
import time
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Agency, Member, MetricDaily, Notification, PlatformAdmin, Post, SocialAccount, now_ms

DAY = 86_400_000
GRACE_DAYS = 3

PLANS: dict[str, dict] = {
    "free": {"label": "Free", "price": 0, "yearlyPrice": 0, "clients": 1, "projects": 1, "members": 1, "aiPerMonth": 20, "reports": False, "aiContent": False, "campaigns": False, "whiteLabel": False},
    "starter": {"label": "Starter", "price": 499, "yearlyPrice": 4990, "clients": 5, "projects": 10, "members": 3, "aiPerMonth": 100, "reports": True, "aiContent": False, "campaigns": False, "whiteLabel": False},
    "pro": {"label": "Pro", "price": 1499, "yearlyPrice": 14990, "clients": 25, "projects": 60, "members": 10, "aiPerMonth": 500, "reports": True, "aiContent": True, "campaigns": True, "whiteLabel": False},
    "agency": {"label": "Agency", "price": 4999, "yearlyPrice": 49990, "clients": 1000, "projects": 5000, "members": 50, "aiPerMonth": 3000, "reports": True, "aiContent": True, "campaigns": True, "whiteLabel": True},
}
PLAN_KEYS = tuple(PLANS)
PLATFORMS = ("instagram", "facebook", "youtube")
ROLES = ("owner", "admin", "manager", "analyst", "content_manager", "viewer")

MANAGE_ROLES = ("owner", "admin", "manager")
CONTENT_ROLES = ("owner", "admin", "manager", "content_manager")
REPORT_ROLES = ("owner", "admin", "manager", "analyst")
ADMIN_ROLES = ("owner", "admin")
ALL_ROLES = ROLES


class ApiError(HTTPException):
    """User-facing error — `detail` is shown in the UI as-is."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(status_code=status_code, detail=message)


# ---------------- dates ----------------

def iso_date(d: date) -> str:
    return d.isoformat()[:10]


def today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def days_ago(n: int) -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=n)).isoformat()


def month_key(ts_ms: int | None = None) -> str:
    dt = datetime.fromtimestamp((ts_ms or now_ms()) / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m")


def parse_date(s: str) -> date:
    return date.fromisoformat(s[:10])


# ---------------- subscription access ----------------

def access_for(agency: Agency, now: int | None = None) -> dict:
    now = now if now is not None else now_ms()

    def days(t: int) -> int:
        return math.ceil((t - now) / DAY)

    if agency.status == "pending":
        return {"state": "pending", "canWrite": False, "endsAt": None, "daysLeft": None}
    if agency.status == "rejected":
        return {"state": "rejected", "canWrite": False, "endsAt": None, "daysLeft": None}
    if agency.status == "suspended":
        return {"state": "suspended", "canWrite": False, "endsAt": None, "daysLeft": None}
    if not agency.subscription_status:
        return {"state": "active", "canWrite": True, "endsAt": None, "daysLeft": None}  # legacy / platform owner
    if agency.subscription_status == "trialing" and agency.trial_ends_at:
        if agency.trial_ends_at > now:
            return {"state": "trial", "canWrite": True, "endsAt": agency.trial_ends_at, "daysLeft": days(agency.trial_ends_at)}
        return {"state": "expired", "canWrite": False, "endsAt": agency.trial_ends_at, "daysLeft": 0}
    if agency.subscription_status == "active" and agency.current_period_end:
        if agency.current_period_end > now:
            return {"state": "active", "canWrite": True, "endsAt": agency.current_period_end, "daysLeft": days(agency.current_period_end)}
        grace_end = agency.current_period_end + GRACE_DAYS * DAY
        if grace_end > now:
            return {"state": "grace", "canWrite": True, "endsAt": grace_end, "daysLeft": days(grace_end)}
    return {"state": "expired", "canWrite": False, "endsAt": agency.current_period_end or agency.trial_ends_at, "daysLeft": 0}


def access_message(a: dict) -> str:
    if a["state"] == "pending":
        return "Aapka account abhi approval ke liye pending hai."
    if a["state"] == "rejected":
        return "Aapka account approve nahi hua. Support se contact karein."
    if a["state"] == "suspended":
        return "Aapka account suspend hai. Support se contact karein."
    return "Aapka trial/subscription khatam ho gaya hai. Billing page se payment karke renew karein."


def require_feature(agency: Agency, feature: str) -> None:
    if not PLANS[agency.plan][feature]:
        raise ApiError(f"Ye feature aapke {PLANS[agency.plan]['label']} plan mein nahi hai. Billing page se upgrade karein.")


# ---------------- notifications ----------------

def notify(db: Session, agency_id: str, kind: str, text: str) -> None:
    db.add(Notification(agency_id=agency_id, kind=kind, text=text[:500], read=False))


def notify_admins(db: Session, text: str) -> None:
    for admin in db.scalars(select(PlatformAdmin)).all():
        m = db.scalar(select(Member).where(Member.user_id == admin.user_id))
        if m:
            notify(db, m.agency_id, "admin", text)


def is_platform_admin(db: Session, user_id: str) -> bool:
    return db.scalar(select(PlatformAdmin).where(PlatformAdmin.user_id == user_id)) is not None


# ---------------- analytics ----------------

def _dates(start: str, end: str) -> list[str]:
    out, d, e = [], parse_date(start), parse_date(end)
    while d <= e:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def series_for_accounts(db: Session, account_ids: list[str], start: str, end: str) -> list[dict]:
    """Daily series summed across accounts. Followers carry forward so mid-period connects don't spike."""
    dates = _dates(start, end)
    by_date = {d: {"date": d, "followers": 0, "views": 0, "likes": 0, "comments": 0, "shares": 0, "posts": 0} for d in dates}
    any_data = False
    for account_id in account_ids:
        rows = db.scalars(
            select(MetricDaily).where(MetricDaily.account_id == account_id, MetricDaily.date >= start, MetricDaily.date <= end).order_by(MetricDaily.date)
        ).all()
        before = db.scalar(
            select(MetricDaily).where(MetricDaily.account_id == account_id, MetricDaily.date < start).order_by(MetricDaily.date.desc()).limit(1)
        )
        earliest = before or (rows[0] if rows else None) or db.scalar(
            select(MetricDaily).where(MetricDaily.account_id == account_id).order_by(MetricDaily.date).limit(1)
        )
        if not earliest:
            continue
        any_data = True
        row_by_date = {r.date: r for r in rows}
        current = earliest.followers
        for d in dates:
            p = by_date[d]
            r = row_by_date.get(d)
            if r:
                current = r.followers
                p["views"] += r.views
                p["likes"] += r.likes
                p["comments"] += r.comments
                p["shares"] += r.shares
                p["posts"] += r.posts_count
            p["followers"] += current
    return [by_date[d] for d in dates] if any_data else []


def summarize(series: list[dict]) -> dict:
    first = series[0] if series else None
    last = series[-1] if series else None

    def total(k: str) -> int:
        return sum(p[k] for p in series)

    views, likes, comments, shares, posts = total("views"), total("likes"), total("comments"), total("shares"), total("posts")
    interactions = likes + comments + shares
    avg_followers = sum(p["followers"] for p in series) / len(series) if series else 0
    base = views if views > 0 else avg_followers
    return {
        "followers": last["followers"] if last else 0,
        "followersStart": first["followers"] if first else 0,
        "followerGrowth": (last["followers"] - first["followers"]) if first and last else 0,
        "growthRate": ((last["followers"] - first["followers"]) / first["followers"] * 100) if first and last and first["followers"] > 0 else 0,
        "views": views,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "posts": posts,
        "engagementRate": (interactions / base * 100) if base > 0 else 0,
    }


def pct_change(curr: float, prev: float) -> float:
    if not prev:
        return 0
    return (curr - prev) / prev * 100


def post_rate(p, followers: int | None = None) -> float:
    inter = p.likes + p.comments + p.shares
    if p.views > 0:
        return inter / p.views * 100
    if followers and followers > 0:
        return inter / followers * 100
    return 0


def with_post_fallback(db: Session, account: SocialAccount, start: str, end: str, s: dict) -> dict:
    """Live accounts only have daily deltas from the connect day; until then use posts published in the period."""
    if account.mode != "api":
        return {**s, "fromPosts": False}
    first_row = db.scalar(select(MetricDaily).where(MetricDaily.account_id == account.id).order_by(MetricDaily.date).limit(1))
    if first_row and first_row.date <= start:
        return {**s, "fromPosts": False}
    posts = db.scalars(select(Post).where(Post.account_id == account.id, Post.published_at >= start, Post.published_at <= end)).all()
    if not posts:
        return {**s, "fromPosts": False}
    views = sum(p.views for p in posts)
    likes = sum(p.likes for p in posts)
    comments = sum(p.comments for p in posts)
    shares = sum(p.shares for p in posts)
    base = views if views > 0 else (account.followers or s["followers"]) * len(posts)
    return {**s, "views": views, "likes": likes, "comments": comments, "shares": shares, "posts": len(posts),
            "engagementRate": ((likes + comments + shares) / base * 100) if base > 0 else 0, "fromPosts": True}


# ---------------- demo data ----------------

def _rng(seed: int):
    state = [seed % 2147483647 or 2147483646]

    def nxt() -> float:
        state[0] = (state[0] * 16807) % 2147483647
        return (state[0] - 1) / 2147483646

    return nxt


def _hash(s: str) -> int:
    h = 0
    for ch in s:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    if h >= 2**31:
        h -= 2**32
    return abs(h) + 1


FORMATS = {"instagram": ["Reel", "Carousel", "Image", "Story"], "facebook": ["Video", "Image", "Link", "Text"], "youtube": ["Video", "Short", "Live"]}
TOPICS = ["Behind the scenes", "Customer story", "Quick tips", "Product spotlight", "FAQ answered", "Team introduction",
          "Before & after", "Myth vs fact", "Weekly update", "Expert interview", "How-to tutorial", "Festival greetings"]


def insert_demo_history(db: Session, agency_id: str, account_id: str, platform: str, username: str, days: int = 365) -> None:
    """Clearly labelled DEMO metrics for an account until a real platform API is connected."""
    r = _rng(_hash(username + platform))
    followers = round(2000 + r() * 40000)
    following = round(150 + r() * 600)
    base_views = followers * (0.6 if platform == "youtube" else 0.35)
    today = datetime.now(timezone.utc).date()
    rows = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        weekend = d.weekday() >= 5
        trend = 1 + (days - i) / days / 2
        views = round(base_views * trend * (0.6 + r() * 0.8) * (1.15 if weekend else 1))
        engagement = 0.04 + r() * 0.06
        likes = round(views * engagement * 0.8)
        comments = round(views * engagement * 0.12)
        shares = round(views * engagement * 0.08)
        followers += round(followers * (0.0008 + r() * 0.0025) - r() * 6)
        rows.append(MetricDaily(agency_id=agency_id, account_id=account_id, date=d.isoformat(), followers=followers, following=following,
                                views=views, likes=likes, comments=comments, shares=shares, posts_count=1 if r() > 0.55 else 0))
    formats = FORMATS[platform]
    for i in range(30):
        d = today - timedelta(days=math.floor(i * 3 + r() * 3))
        fmt = formats[math.floor(r() * len(formats))]
        boost = 1.6 if fmt in ("Reel", "Short", "Video") else 1
        views = round(base_views * 2.5 * boost * (0.4 + r() * 1.4))
        eng = 0.05 + r() * 0.07
        rows.append(Post(agency_id=agency_id, account_id=account_id, platform=platform, format=fmt,
                         title=f"{TOPICS[math.floor(r() * len(TOPICS))]} — {fmt}", published_at=d.isoformat(), views=views,
                         likes=round(views * eng * 0.82), comments=round(views * eng * 0.1), shares=round(views * eng * 0.08)))
    db.add_all(rows)


def epoch_ms() -> int:
    return int(time.time() * 1000)
