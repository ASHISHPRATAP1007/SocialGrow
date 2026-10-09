"""Clients, projects, social accounts, goals, campaigns and content calendar."""
from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..core.deps import Workspace, read_ws, require_ws
from ..core.lib import (
    CONTENT_ROLES, MANAGE_ROLES, PLANS, PLATFORMS, ApiError, days_ago, insert_demo_history, notify, parse_date, require_feature, today_iso,
)
from ..core.serialize import to_dict
from ..database import get_db
from ..models import Campaign, Client, ContentItem, Goal, MetricDaily, Post, Project, SocialAccount

router = APIRouter(tags=["entities"])


def _owned(db: Session, model, agency_id: str, obj_id: str | None, label: str):
    obj = db.get(model, obj_id) if obj_id else None
    if not obj or obj.agency_id != agency_id:
        raise ApiError(f"{label} nahi mila.", 404)
    return obj


def _check_platform(p: str):
    if p not in PLATFORMS:
        raise ApiError("Platform galat hai.")


# ---------------- clients ----------------

class ClientIn(BaseModel):
    name: str
    company: str | None = None
    email: str | None = None
    phone: str | None = None


@router.get("/clients")
def list_clients(ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    clients = db.scalars(select(Client).where(Client.agency_id == ws.agency.id).order_by(Client.created_at)).all()
    projects = db.scalars(select(Project).where(Project.agency_id == ws.agency.id)).all()
    accounts = db.scalars(select(SocialAccount).where(SocialAccount.agency_id == ws.agency.id)).all()
    return [
        to_dict(c) | {
            "projectCount": sum(1 for p in projects if p.client_id == c.id),
            "platforms": sorted({a.platform for a in accounts if a.client_id == c.id}),
        }
        for c in clients
    ]


@router.post("/clients")
def create_client(body: ClientIn, ws: Workspace = Depends(require_ws(MANAGE_ROLES)), db: Session = Depends(get_db)):
    count = db.scalar(select(func.count()).select_from(Client).where(Client.agency_id == ws.agency.id))
    limit = PLANS[ws.agency.plan]["clients"]
    if count >= limit:
        raise ApiError(f"{PLANS[ws.agency.plan]['label']} plan mein {limit} client(s) allowed hain. Upgrade karein.")
    if not body.name.strip():
        raise ApiError("Client name zaroori hai.")
    c = Client(agency_id=ws.agency.id, name=body.name.strip(), company=body.company or None, email=body.email or None, phone=body.phone or None)
    db.add(c)
    db.commit()
    return {"id": c.id}


@router.delete("/clients/{client_id}")
def delete_client(client_id: str, ws: Workspace = Depends(require_ws(MANAGE_ROLES)), db: Session = Depends(get_db)):
    c = _owned(db, Client, ws.agency.id, client_id, "Client")
    if db.scalar(select(Project).where(Project.client_id == c.id)):
        raise ApiError("Pehle is client ke projects delete karein.")
    db.delete(c)
    db.commit()
    return {"ok": True}


# ---------------- projects ----------------

class ProjectIn(BaseModel):
    clientId: str
    name: str
    platforms: list[str]
    startDate: str
    endDate: str


class StatusIn(BaseModel):
    status: str


@router.get("/projects")
def list_projects(ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    projects = db.scalars(select(Project).where(Project.agency_id == ws.agency.id).order_by(Project.created_at)).all()
    clients = {c.id: c.name for c in db.scalars(select(Client).where(Client.agency_id == ws.agency.id)).all()}
    accounts = db.scalars(select(SocialAccount).where(SocialAccount.agency_id == ws.agency.id)).all()
    return [
        to_dict(p) | {"clientName": clients.get(p.client_id, "—"), "accountCount": sum(1 for a in accounts if a.project_id == p.id)}
        for p in projects
    ]


@router.post("/projects")
def create_project(body: ProjectIn, ws: Workspace = Depends(require_ws(MANAGE_ROLES)), db: Session = Depends(get_db)):
    _owned(db, Client, ws.agency.id, body.clientId, "Client")
    count = db.scalar(select(func.count()).select_from(Project).where(Project.agency_id == ws.agency.id))
    limit = PLANS[ws.agency.plan]["projects"]
    if count >= limit:
        raise ApiError(f"{PLANS[ws.agency.plan]['label']} plan mein {limit} project(s) allowed hain. Upgrade karein.")
    if not body.name.strip():
        raise ApiError("Project name zaroori hai.")
    if body.endDate < body.startDate:
        raise ApiError("End date start date ke baad honi chahiye.")
    for p in body.platforms:
        _check_platform(p)
    p = Project(agency_id=ws.agency.id, client_id=body.clientId, name=body.name.strip(), platforms=list(dict.fromkeys(body.platforms)),
                start_date=body.startDate, end_date=body.endDate, status="active")
    db.add(p)
    db.commit()
    return {"id": p.id}


@router.patch("/projects/{project_id}")
def set_project_status(project_id: str, body: StatusIn, ws: Workspace = Depends(require_ws(MANAGE_ROLES)), db: Session = Depends(get_db)):
    p = _owned(db, Project, ws.agency.id, project_id, "Project")
    if body.status not in ("active", "paused", "completed"):
        raise ApiError("Status galat hai.")
    p.status = body.status
    db.commit()
    return {"ok": True}


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, ws: Workspace = Depends(require_ws(MANAGE_ROLES)), db: Session = Depends(get_db)):
    p = _owned(db, Project, ws.agency.id, project_id, "Project")
    if db.scalar(select(SocialAccount).where(SocialAccount.project_id == p.id)):
        raise ApiError("Pehle is project ke social accounts disconnect karein.")
    db.delete(p)
    db.commit()
    return {"ok": True}


# ---------------- social accounts ----------------

class DemoConnectIn(BaseModel):
    projectId: str
    platform: str
    username: str


@router.get("/accounts")
def list_accounts(ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    accounts = db.scalars(select(SocialAccount).where(SocialAccount.agency_id == ws.agency.id).order_by(SocialAccount.created_at)).all()
    projects = {p.id: p.name for p in db.scalars(select(Project).where(Project.agency_id == ws.agency.id)).all()}
    clients = {c.id: c.name for c in db.scalars(select(Client).where(Client.agency_id == ws.agency.id)).all()}
    out = []
    for a in accounts:
        followers = a.followers
        if followers is None:
            latest = db.scalar(select(MetricDaily).where(MetricDaily.account_id == a.id).order_by(MetricDaily.date.desc()).limit(1))
            followers = latest.followers if latest else None
        out.append(to_dict(a) | {"followers": followers, "projectName": projects.get(a.project_id, "—"), "clientName": clients.get(a.client_id, "—")})
    return out


@router.post("/accounts/demo")
def connect_demo_account(body: DemoConnectIn, ws: Workspace = Depends(require_ws(MANAGE_ROLES)), db: Session = Depends(get_db)):
    _check_platform(body.platform)
    project = _owned(db, Project, ws.agency.id, body.projectId, "Project")
    username = body.username.strip().lstrip("@")
    if not username:
        raise ApiError("Username daalein.")
    acc = SocialAccount(agency_id=ws.agency.id, project_id=project.id, client_id=project.client_id, platform=body.platform,
                        username=username, mode="demo", status="connected")
    db.add(acc)
    db.flush()
    if body.platform not in (project.platforms or []):
        project.platforms = [*(project.platforms or []), body.platform]
    insert_demo_history(db, ws.agency.id, acc.id, body.platform, username)
    notify(db, ws.agency.id, "account", f"@{username} ({body.platform}) demo mode mein connect hua")
    db.commit()
    return {"id": acc.id}


@router.delete("/accounts/{account_id}")
def disconnect_account(account_id: str, ws: Workspace = Depends(require_ws(MANAGE_ROLES)), db: Session = Depends(get_db)):
    a = _owned(db, SocialAccount, ws.agency.id, account_id, "Account")
    db.execute(delete(MetricDaily).where(MetricDaily.account_id == a.id))
    db.execute(delete(Post).where(Post.account_id == a.id))
    db.execute(delete(Goal).where(Goal.account_id == a.id))
    db.delete(a)
    db.commit()
    return {"ok": True}


# ---------------- goals ----------------

class GoalIn(BaseModel):
    accountId: str
    target: float
    days: float


@router.get("/goals")
def list_goals(ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    out = []
    for g in db.scalars(select(Goal).where(Goal.agency_id == ws.agency.id).order_by(Goal.created_at)).all():
        account = db.get(SocialAccount, g.account_id)
        rows = db.scalars(select(MetricDaily).where(MetricDaily.account_id == g.account_id, MetricDaily.date >= g.start_date,
                                                    MetricDaily.date <= g.end_date).order_by(MetricDaily.date)).all()
        current = rows[-1].followers if rows else g.start_value
        gained = current - g.start_value
        needed = g.target - g.start_value
        out.append(to_dict(g) | {
            "account": f"{account.platform} · @{account.username}" if account else "—",
            "current": current,
            "gained": gained,
            "progress": max(0, min(100, gained / needed * 100)) if needed > 0 else 100,
            "history": [{"date": r.date, "followers": r.followers} for r in rows],
        })
    return out


@router.post("/goals")
def create_goal(body: GoalIn, ws: Workspace = Depends(require_ws(MANAGE_ROLES)), db: Session = Depends(get_db)):
    a = _owned(db, SocialAccount, ws.agency.id, body.accountId, "Account")
    # Goal starts 14 days back so progress is visible immediately with existing history
    start_date = days_ago(14)
    end_date = (parse_date(start_date) + timedelta(days=max(1, round(body.days)))).isoformat()
    first = db.scalar(select(MetricDaily).where(MetricDaily.account_id == a.id, MetricDaily.date >= start_date).order_by(MetricDaily.date).limit(1))
    start_value = first.followers if first else (a.followers or 0)
    if body.target <= start_value:
        raise ApiError(f"Target current followers ({start_value}) se zyada hona chahiye.")
    db.add(Goal(agency_id=ws.agency.id, account_id=a.id, start_value=start_value, target=round(body.target), start_date=start_date, end_date=end_date))
    notify(db, ws.agency.id, "goal", f"@{a.username} ke liye {round(body.target):,} followers ka goal set hua")
    db.commit()
    return {"ok": True}


@router.delete("/goals/{goal_id}")
def delete_goal(goal_id: str, ws: Workspace = Depends(require_ws(MANAGE_ROLES)), db: Session = Depends(get_db)):
    db.delete(_owned(db, Goal, ws.agency.id, goal_id, "Goal"))
    db.commit()
    return {"ok": True}


# ---------------- campaigns ----------------

class CampaignIn(BaseModel):
    clientId: str
    name: str
    platform: str
    goal: str
    startDate: str
    endDate: str
    budget: float
    contentPlanned: int


class DeltaIn(BaseModel):
    delta: int


@router.get("/campaigns")
def list_campaigns(ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    campaigns = db.scalars(select(Campaign).where(Campaign.agency_id == ws.agency.id).order_by(Campaign.created_at.desc())).all()
    clients = {c.id: c.name for c in db.scalars(select(Client).where(Client.agency_id == ws.agency.id)).all()}
    accounts = db.scalars(select(SocialAccount).where(SocialAccount.agency_id == ws.agency.id)).all()
    out = []
    for c in campaigns:
        ids = [a.id for a in accounts if a.client_id == c.client_id and a.platform == c.platform]
        views = inter = 0
        if ids:
            for r in db.scalars(select(MetricDaily).where(MetricDaily.account_id.in_(ids), MetricDaily.date >= c.start_date, MetricDaily.date <= c.end_date)).all():
                views += r.views
                inter += r.likes + r.comments + r.shares
        out.append(to_dict(c) | {
            "clientName": clients.get(c.client_id, "—"),
            "engagementRate": inter / views * 100 if views else 0,
            "progress": min(100, c.content_published / c.content_planned * 100) if c.content_planned else 0,
        })
    return out


@router.post("/campaigns")
def create_campaign(body: CampaignIn, ws: Workspace = Depends(require_ws(MANAGE_ROLES)), db: Session = Depends(get_db)):
    require_feature(ws.agency, "campaigns")
    _owned(db, Client, ws.agency.id, body.clientId, "Client")
    _check_platform(body.platform)
    if not body.name.strip():
        raise ApiError("Campaign name daalein.")
    if body.endDate < body.startDate:
        raise ApiError("End date start date ke baad honi chahiye.")
    today = today_iso()
    status = "planned" if body.startDate > today else "completed" if body.endDate < today else "active"
    db.add(Campaign(agency_id=ws.agency.id, client_id=body.clientId, name=body.name.strip(), platform=body.platform, goal=body.goal,
                    start_date=body.startDate, end_date=body.endDate, budget=body.budget, status=status,
                    content_planned=max(0, body.contentPlanned), content_published=0))
    notify(db, ws.agency.id, "campaign", f'Naya campaign "{body.name.strip()}" bana')
    db.commit()
    return {"ok": True}


@router.patch("/campaigns/{campaign_id}/progress")
def update_campaign_progress(campaign_id: str, body: DeltaIn, ws: Workspace = Depends(require_ws(CONTENT_ROLES)), db: Session = Depends(get_db)):
    c = _owned(db, Campaign, ws.agency.id, campaign_id, "Campaign")
    c.content_published = max(0, min(c.content_planned, c.content_published + body.delta))
    db.commit()
    return {"ok": True}


@router.delete("/campaigns/{campaign_id}")
def delete_campaign(campaign_id: str, ws: Workspace = Depends(require_ws(MANAGE_ROLES)), db: Session = Depends(get_db)):
    db.delete(_owned(db, Campaign, ws.agency.id, campaign_id, "Campaign"))
    db.commit()
    return {"ok": True}


# ---------------- content calendar ----------------

class ContentIn(BaseModel):
    clientId: str | None = None
    date: str
    platform: str
    format: str
    topic: str
    notes: str | None = None


@router.get("/content")
def list_content(month: str, ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    items = db.scalars(select(ContentItem).where(ContentItem.agency_id == ws.agency.id, ContentItem.date >= f"{month}-01",
                                                 ContentItem.date <= f"{month}-31").order_by(ContentItem.date)).all()
    clients = {c.id: c.name for c in db.scalars(select(Client).where(Client.agency_id == ws.agency.id)).all()}
    return [to_dict(i) | {"clientName": clients.get(i.client_id)} for i in items]


@router.post("/content")
def add_content_item(body: ContentIn, ws: Workspace = Depends(require_ws(CONTENT_ROLES)), db: Session = Depends(get_db)):
    _check_platform(body.platform)
    if body.clientId:
        _owned(db, Client, ws.agency.id, body.clientId, "Client")
    if not body.topic.strip():
        raise ApiError("Topic daalein.")
    db.add(ContentItem(agency_id=ws.agency.id, client_id=body.clientId or None, date=body.date, platform=body.platform,
                       format=body.format[:30], topic=body.topic.strip()[:200], notes=body.notes, status="idea"))
    db.commit()
    return {"ok": True}


@router.patch("/content/{item_id}")
def set_content_status(item_id: str, body: StatusIn, ws: Workspace = Depends(require_ws(CONTENT_ROLES)), db: Session = Depends(get_db)):
    i = _owned(db, ContentItem, ws.agency.id, item_id, "Item")
    if body.status not in ("idea", "scheduled", "published"):
        raise ApiError("Status galat hai.")
    i.status = body.status
    db.commit()
    return {"ok": True}


@router.delete("/content/{item_id}")
def delete_content_item(item_id: str, ws: Workspace = Depends(require_ws(CONTENT_ROLES)), db: Session = Depends(get_db)):
    db.delete(_owned(db, ContentItem, ws.agency.id, item_id, "Item"))
    db.commit()
    return {"ok": True}
