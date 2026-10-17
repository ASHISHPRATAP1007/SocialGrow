"""AI features: insights, growth analyst, content assistant, post analyzer, content calendar, client reports."""
import json
from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.deps import Workspace, read_ws, require_ws
from ..core.lib import ALL_ROLES, CONTENT_ROLES, PLANS, PLATFORMS, REPORT_ROLES, ApiError, month_key, notify, parse_date, post_rate
from ..core.serialize import to_dict
from ..database import get_db
from ..models import AiLog, Client, ContentItem, Post, Report, SocialAccount
from ..services.ai_service import llm, parse_json
from ..services.analytics_service import analytics_snapshot, report_data

router = APIRouter(tags=["ai"])


def gate(db: Session, ws: Workspace, kind: str, feature: str | None = None) -> None:
    limits = PLANS[ws.agency.plan]
    if feature and not limits[feature]:
        raise ApiError(f"Ye AI feature aapke {limits['label']} plan mein nahi hai. Billing se upgrade karein.")
    used = db.scalar(select(func.count()).select_from(AiLog).where(AiLog.agency_id == ws.agency.id, AiLog.month == month_key())) or 0
    if used >= limits["aiPerMonth"]:
        raise ApiError(f"Is mahine ki AI limit ({limits['aiPerMonth']} requests) poori ho gayi. Plan upgrade karein.")
    db.add(AiLog(agency_id=ws.agency.id, user_id=ws.user.id, kind=kind, month=month_key()))
    db.commit()


class DaysIn(BaseModel):
    days: int = 30


@router.post("/ai/insights")
def insights(body: DaysIn, ws: Workspace = Depends(require_ws(ALL_ROLES)), db: Session = Depends(get_db)):
    gate(db, ws, "insight")
    data = analytics_snapshot(db, ws.agency.id, body.days)
    if not data:
        return {"text": "Abhi koi social account connect nahi hai. Social Accounts page se account connect karein, phir AI insights milenge."}
    return {"text": llm(
        f"Analytics for the last {body.days} days vs the previous {body.days} days (JSON):\n{json.dumps(data)}\n\n"
        'Write 3-5 short bullet insights (start each with "• "). Mention concrete numbers from the data, which content formats work best, '
        "and one clear next action. Max 120 words. No headings.")}


class AnalystIn(BaseModel):
    question: str
    days: int = 30
    accountId: str | None = None


@router.post("/ai/analyst")
def ask_analyst(body: AnalystIn, ws: Workspace = Depends(require_ws(ALL_ROLES)), db: Session = Depends(get_db)):
    if not body.question.strip():
        raise ApiError("Sawal likhein.")
    gate(db, ws, "analyst", "aiContent")
    data = analytics_snapshot(db, ws.agency.id, body.days, account_id=body.accountId)
    if not data:
        return {"text": "Analyse karne ke liye koi connected account nahi mila."}
    return {"text": llm(
        f'User question: "{body.question.strip()}"\n\nAnalytics data, current {body.days}-day period vs previous period (JSON):\n{json.dumps(data)}\n\n'
        "Answer in this markdown structure:\n### Short answer\n(1-2 sentences)\n### What the data shows\n(3-5 bullets with numbers)\n"
        '### Possible data-backed factors\n(bullets; say "possible" when it is correlation)\n### Recommended actions\n(numbered list, 3-5 concrete steps)\n'
        "If the user writes in Hinglish, reply in simple Hinglish.")}


class ContentIn(BaseModel):
    platform: str
    topic: str
    audience: str
    tone: str
    language: str


@router.post("/ai/content")
def content_assistant(body: ContentIn, ws: Workspace = Depends(require_ws(CONTENT_ROLES)), db: Session = Depends(get_db)):
    if not body.topic.strip():
        raise ApiError("Topic daalein.")
    gate(db, ws, "content", "aiContent")
    text = llm(
        f"Create social media content suggestions.\nPlatform: {body.platform}\nTopic/business: {body.topic}\nAudience: {body.audience}\n"
        f"Tone: {body.tone}\nLanguage: {body.language}\n\nReturn ONLY valid JSON with keys: "
        '{"hooks": string[3], "captions": string[2], "cta": string[3], "contentIdeas": string[5], "hashtags": string[12], '
        '"reelIdeas": string[3], "carouselIdeas": string[3]}. Hashtags include the # sign. No fake engagement tactics.')
    try:
        return parse_json(text)
    except Exception:
        return {"contentIdeas": [text]}


class PostIn(BaseModel):
    postId: str


@router.post("/ai/analyze-post")
def analyze_content(body: PostIn, ws: Workspace = Depends(require_ws(ALL_ROLES)), db: Session = Depends(get_db)):
    p = db.get(Post, body.postId)
    if not p or p.agency_id != ws.agency.id:
        raise ApiError("Post nahi mila.", 404)
    gate(db, ws, "analyze", "aiContent")
    acc = db.get(SocialAccount, p.account_id)
    followers = acc.followers if acc else None
    siblings = db.scalars(select(Post).where(Post.account_id == p.account_id)).all()
    data = {
        "post": {"title": p.title, "format": p.format, "platform": p.platform, "date": p.published_at, "views": p.views, "likes": p.likes,
                 "comments": p.comments, "shares": p.shares, "engagementRate": round(post_rate(p, followers), 2)},
        "accountAverage": {"engagementRate": round(sum(post_rate(x, followers) for x in siblings) / max(1, len(siblings)), 2),
                           "views": round(sum(x.views for x in siblings) / max(1, len(siblings))), "posts": len(siblings)},
    }
    text = llm(
        f"Analyse this post against the account average (JSON):\n{json.dumps(data)}\n\nOnly the title, format and metrics are known (not the visual). "
        'Return ONLY valid JSON: {"hook": "Strong|Good|Needs improvement", "clarity": "...", "cta": "...", "engagement": "Above average|Average|Below average", '
        '"summary": string, "suggestions": string[4]}.')
    try:
        return {**parse_json(text), "metrics": data}
    except Exception:
        return {"summary": text, "suggestions": [], "metrics": data}


class CalendarIn(BaseModel):
    clientId: str | None = None
    platforms: list[str]
    topic: str = ""
    startDate: str
    days: int = 30
    replace: bool = True  # regenerate: remove this client's unused AI ideas in the same dates first


def _client_context(db: Session, client: Client) -> str:
    """What this client's own accounts show: platforms, size, best formats and best posts — so the plan fits them."""
    accounts = db.scalars(select(SocialAccount).where(SocialAccount.client_id == client.id)).all()
    if not accounts:
        return ""
    lines = []
    for a in accounts:
        posts = db.scalars(select(Post).where(Post.account_id == a.id).order_by(Post.published_at.desc()).limit(50)).all()
        if posts:
            by_fmt: dict[str, list[float]] = {}
            for p in posts:
                by_fmt.setdefault(p.format, []).append(post_rate(p, a.followers))
            fmts = sorted(((f, sum(r) / len(r)) for f, r in by_fmt.items()), key=lambda x: -x[1])
            top = sorted(posts, key=lambda p: -(p.views or p.likes))[:3]
            lines.append(f"- {a.platform} @{a.username}: {a.followers or 0} followers; best formats: "
                         + ", ".join(f"{f} ({r:.1f}% eng.)" for f, r in fmts[:3])
                         + "; top posts: " + " | ".join(p.title[:60] for p in top))
        else:
            lines.append(f"- {a.platform} @{a.username}: {a.followers or 0} followers; no posts yet")
    return "This client's own accounts (use this to choose formats and themes that already work):\n" + "\n".join(lines)


@router.post("/ai/calendar")
def generate_calendar(body: CalendarIn, ws: Workspace = Depends(require_ws(CONTENT_ROLES)), db: Session = Depends(get_db)):
    platforms = [p for p in body.platforms if p in PLATFORMS]
    if not platforms:
        raise ApiError("Kam se kam ek platform chunein.")
    client = None
    if body.clientId:
        client = db.get(Client, body.clientId)
        if not client or client.agency_id != ws.agency.id:
            raise ApiError("Client nahi mila.", 404)
    topic = body.topic.strip() or (f"{client.name}" + (f" ({client.company})" if client and client.company else "") if client else "")
    if not topic:
        raise ApiError("Business / topic likhein ya client chunein.")
    gate(db, ws, "calendar", "aiContent")
    days = max(7, min(31, round(body.days)))
    context = _client_context(db, client) if client else ""
    text = llm(
        f"Create a {days}-day social media content plan starting {body.startDate}.\nBusiness/topic: {topic}\n"
        + (f"Client: {client.name}\n{context}\n" if client else "")
        + f"Platforms: {', '.join(platforms)}\n"
        "One item per day. Mix formats (instagram: Reel/Carousel/Story/Image, facebook: Video/Image/Post, youtube: Short/Video).\n"
        f'Return ONLY a JSON array of exactly {days} objects: {{"day": number (1-based), "platform": one of {json.dumps(platforms)}, '
        '"format": string, "topic": string (max 10 words), "notes": string (one line idea)}.')
    try:
        items = parse_json(text)
    except Exception:
        raise ApiError("AI calendar parse nahi ho paya, dobara try karein.")
    start = parse_date(body.startDate)
    if body.replace:
        end = (start + timedelta(days=days - 1)).isoformat()
        q = select(ContentItem).where(ContentItem.agency_id == ws.agency.id, ContentItem.status == "idea",
                                      ContentItem.date >= start.isoformat(), ContentItem.date <= end)
        q = q.where(ContentItem.client_id == client.id) if client else q.where(ContentItem.client_id.is_(None))
        for old in db.scalars(q).all():
            db.delete(old)
    count = 0
    for idx, it in enumerate(items[:days]):
        day = it.get("day") if isinstance(it.get("day"), int) else idx + 1
        platform = it.get("platform") if it.get("platform") in platforms else platforms[idx % len(platforms)]
        db.add(ContentItem(agency_id=ws.agency.id, client_id=body.clientId or None, date=(start + timedelta(days=day - 1)).isoformat(),
                           platform=platform, format=str(it.get("format") or "Post")[:30], topic=str(it.get("topic") or "Content idea")[:120],
                           notes=str(it["notes"])[:240] if it.get("notes") else None, status="idea"))
        count += 1
    notify(db, ws.agency.id, "calendar", f"AI ne {count} content ideas{f' ({client.name})' if client else ''} calendar mein add kiye")
    db.commit()
    return {"count": count}


# ---------------- reports ----------------

class ReportIn(BaseModel):
    clientId: str
    type: str
    start: str
    end: str


@router.post("/reports")
def generate_report(body: ReportIn, ws: Workspace = Depends(require_ws(REPORT_ROLES)), db: Session = Depends(get_db)):
    if body.end < body.start:
        raise ApiError("End date start date ke baad honi chahiye.")
    data = report_data(db, ws.agency.id, body.clientId, body.start, body.end)
    if not data:
        raise ApiError("Client nahi mila.", 404)
    if not data["accounts"]:
        raise ApiError("Is client ka koi social account connect nahi hai.")
    gate(db, ws, "report", "reports")
    try:
        summary = llm(
            f"Write a client-facing {body.type} social media report for {data['client']['name']} ({body.start} to {body.end}).\n"
            f"Data (current vs previous equal period):\n{json.dumps(data['accounts'])}\n\nUse this markdown structure exactly:\n"
            "### Executive summary\n### What improved\n### What declined\n### Top content\n### Key observations\n### Recommended next steps\n"
            "Bullets under each, with real numbers. Professional tone. Max 350 words.")
    except ApiError:
        summary = "### Executive summary\nAI summary is waqt available nahi tha. Upar diye gaye numbers period ka performance dikhate hain."
    r = Report(agency_id=ws.agency.id, client_id=body.clientId, type=body.type, period_start=body.start, period_end=body.end,
               data=json.dumps(data), ai_summary=summary, created_by=ws.user.id)
    db.add(r)
    notify(db, ws.agency.id, "report", f"{data['client']['name']} ki {body.type} report ready hai")
    db.commit()
    return {"id": r.id}


@router.get("/reports")
def list_reports(ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    reports = db.scalars(select(Report).where(Report.agency_id == ws.agency.id).order_by(Report.created_at.desc()).limit(100)).all()
    clients = {c.id: c.name for c in db.scalars(select(Client).where(Client.agency_id == ws.agency.id)).all()}
    return [{"id": r.id, "type": r.type, "periodStart": r.period_start, "periodEnd": r.period_end, "createdAt": r.created_at,
             "clientName": clients.get(r.client_id, "—")} for r in reports]


@router.get("/reports/{report_id}")
def get_report(report_id: str, ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    r = db.get(Report, report_id)
    if not r or r.agency_id != ws.agency.id:
        raise ApiError("Report nahi mili.", 404)
    client = db.get(Client, r.client_id)
    a = ws.agency
    return to_dict(r) | {
        "clientName": client.name if client else "—",
        "company": client.company if client else "",
        "brand": {"name": a.brand_name or a.name, "color": a.brand_color, "footer": a.report_footer,
                  "hidePoweredBy": bool(a.hide_social_grow_branding) and a.plan == "agency"},
    }
