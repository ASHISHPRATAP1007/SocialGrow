from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.deps import Workspace, require_ws
from ..core.lib import ApiError, days_ago, insert_demo_history, notify
from ..database import get_db
from ..models import Campaign, Client, ContentItem, Goal, MetricDaily, Project, SocialAccount

router = APIRouter(tags=["demo"])

DEMO = [
    {"client": "ABC Hospital", "company": "ABC Hospital Pvt Ltd", "email": "marketing@abchospital.example",
     "projects": [{"name": "ABC Hospital Social Growth", "accounts": [("instagram", "abchospital"), ("facebook", "abchospital.official"), ("youtube", "ABCHospitalHealth")]}]},
    {"client": "SmileCare Dental", "company": "SmileCare Clinics", "email": "hello@smilecare.example",
     "projects": [{"name": "Instagram Growth", "accounts": [("instagram", "smilecare.dental")]},
                  {"name": "YouTube Education", "accounts": [("youtube", "SmileCareTV")]}]},
]


def seed_agency(db: Session, agency_id: str) -> None:
    if db.scalar(select(Client).where(Client.agency_id == agency_id)):
        raise ApiError("Workspace mein pehle se data hai.")
    client_ids: list[str] = []
    first_account: str | None = None
    for c in DEMO:
        client = Client(agency_id=agency_id, name=c["client"], company=c["company"], email=c["email"], phone="+91 98765 43210")
        db.add(client)
        db.flush()
        client_ids.append(client.id)
        for p in c["projects"]:
            project = Project(agency_id=agency_id, client_id=client.id, name=p["name"], platforms=[a[0] for a in p["accounts"]],
                              start_date=days_ago(60), end_date=days_ago(-30), status="active")
            db.add(project)
            db.flush()
            for platform, username in p["accounts"]:
                acc = SocialAccount(agency_id=agency_id, project_id=project.id, client_id=client.id, platform=platform,
                                    username=username, mode="demo", status="connected")
                db.add(acc)
                db.flush()
                first_account = first_account or acc.id
                insert_demo_history(db, agency_id, acc.id, platform, username)
    db.flush()
    if first_account:
        first = db.scalar(select(MetricDaily).where(MetricDaily.account_id == first_account, MetricDaily.date >= days_ago(14)).order_by(MetricDaily.date).limit(1))
        start = first.followers if first else 1000
        db.add(Goal(agency_id=agency_id, account_id=first_account, start_value=start, target=round(start * 1.08), start_date=days_ago(14), end_date=days_ago(-16)))
    db.add(Campaign(agency_id=agency_id, client_id=client_ids[0], name="Heart Health Awareness Month", platform="instagram", goal="Engagement",
                    start_date=days_ago(20), end_date=days_ago(-10), budget=25000, status="active", content_planned=24, content_published=18))
    db.add(Campaign(agency_id=agency_id, client_id=client_ids[1], name="Free Dental Check-up Drive", platform="youtube", goal="Awareness",
                    start_date=days_ago(5), end_date=days_ago(-25), budget=15000, status="active", content_planned=10, content_published=3))
    ideas = [("instagram", "Reel", "5 signs you should see a cardiologist"), ("instagram", "Carousel", "Healthy heart diet myths"),
             ("facebook", "Video", "Doctor Q&A live recap"), ("youtube", "Short", "Brushing mistakes in 30 seconds"),
             ("instagram", "Story", "Poll: How often do you get a check-up?"), ("youtube", "Video", "Root canal explained simply")]
    for i, (platform, fmt, topic) in enumerate(ideas):
        db.add(ContentItem(agency_id=agency_id, client_id=client_ids[1 if platform == "youtube" else 0], date=days_ago(-(i * 2 + 1)),
                           platform=platform, format=fmt, topic=topic, status="scheduled" if i < 2 else "idea"))
    notify(db, agency_id, "demo", "Demo data load ho gaya — 2 clients, 3 projects, 5 accounts (DEMO label ke saath)")
    db.commit()


@router.post("/demo-data")
def load_demo_data(ws: Workspace = Depends(require_ws(("owner", "admin"))), db: Session = Depends(get_db)):
    seed_agency(db, ws.agency.id)
    return {"ok": True}
