"""End-to-end API tests on a throwaway SQLite database.  Run:  pytest -q   (from the backend folder)"""
import json
import os
import tempfile
import time
import unittest
from unittest import mock

_db = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
os.environ["ENABLE_SCHEDULER"] = "false"
os.environ["CRON_SECRET"] = "cron-test"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.lib import DAY  # noqa: E402
from app.core.security import hmac_sha256_hex  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Agency, PlatformSettings  # noqa: E402

API = "/api/v1"
PW = "SocialGrow@2026"


class Api(unittest.TestCase):
    client: TestClient

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()
        cls.owner = cls.register("owner@test.dev", "Platform Owner")  # first user = platform admin
        cls.agency = cls.register("agency@test.dev", "Sharma Digital", "9876543210")

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    @classmethod
    def register(cls, email, agency_name, phone=None):
        r = cls.client.post(f"{API}/auth/register", json={"email": email, "password": PW, "agencyName": agency_name, "phone": phone})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['accessToken']}"}

    def get(self, path, h, **kw):
        return self.client.get(f"{API}{path}", headers=h, **kw)

    def post(self, path, h, body=None):
        return self.client.post(f"{API}{path}", headers=h, json=body or {})

    def _agency_id(self, h):
        return self.get("/me", h).json()["agency"]["id"]

    # ---------------- auth & workspace ----------------

    def test_01_first_user_is_platform_admin_others_get_trial(self):
        me_owner = self.get("/me", self.owner).json()
        self.assertTrue(me_owner["isPlatformAdmin"])
        self.assertEqual(me_owner["access"]["state"], "active")
        me = self.get("/me", self.agency).json()
        self.assertFalse(me["isPlatformAdmin"])
        self.assertEqual(me["access"]["state"], "trial")
        self.assertEqual(me["access"]["daysLeft"], 30)
        self.assertEqual(me["limits"]["label"], "Pro")
        self.assertNotIn("razorpaySubscriptionId", me["agency"])

    def test_02_login_and_bad_password(self):
        self.assertEqual(self.client.post(f"{API}/auth/login", json={"email": "agency@test.dev", "password": PW}).status_code, 200)
        r = self.client.post(f"{API}/auth/login", json={"email": "agency@test.dev", "password": "wrong-pass"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["detail"], "Email ya password galat hai.")
        self.assertEqual(self.client.get(f"{API}/me").status_code, 401)

    def test_03_duplicate_signup_and_short_password(self):
        r = self.client.post(f"{API}/auth/register", json={"email": "agency@test.dev", "password": PW})
        self.assertIn("pehle se", r.json()["detail"])
        r = self.client.post(f"{API}/auth/register", json={"email": "x@test.dev", "password": "short"})
        self.assertEqual(r.status_code, 400)

    def test_04_forgot_password_without_smtp_is_clear(self):
        r = self.client.post(f"{API}/auth/forgot-password", json={"email": "agency@test.dev"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("support", r.json()["detail"].lower())
        # unknown email: no enumeration
        self.assertEqual(self.client.post(f"{API}/auth/forgot-password", json={"email": "nobody@test.dev"}).status_code, 200)

    # ---------------- demo data + analytics ----------------

    def test_10_demo_data_and_analytics(self):
        self.assertEqual(self.post("/demo-data", self.agency).status_code, 200)
        self.assertEqual(self.post("/demo-data", self.agency).json()["detail"], "Workspace mein pehle se data hai.")
        clients = self.get("/clients", self.agency).json()
        self.assertEqual(len(clients), 2)
        accounts = self.get("/accounts", self.agency).json()
        self.assertEqual(len(accounts), 5)
        self.assertTrue(all(a["followers"] for a in accounts))
        ov = self.get("/analytics/overview", self.agency, params={"days": 30}).json()
        self.assertEqual(ov["accountCount"], 5)
        self.assertTrue(ov["hasDemo"])
        self.assertEqual(len(ov["chart"]), 30)
        self.assertGreater(ov["totals"]["engagementRate"], 0)
        self.assertLess(ov["totals"]["engagementRate"], 50)
        self.assertEqual({p["platform"] for p in ov["perPlatform"]}, {"instagram", "facebook", "youtube"})
        year = self.get("/analytics/overview", self.agency, params={"days": 365}).json()
        self.assertLess(len(year["chart"]), 60)  # weekly buckets
        posts = self.get("/posts", self.agency, params={"days": 90, "sort": "views"}).json()
        self.assertTrue(posts and posts[0]["views"] >= posts[-1]["views"])
        self.assertEqual(len(self.get("/goals", self.agency).json()), 1)
        self.assertEqual(len(self.get("/campaigns", self.agency).json()), 2)

    def test_11_client_project_account_crud(self):
        c = self.post("/clients", self.agency, {"name": "Dr Atul"}).json()["id"]
        p = self.post("/projects", self.agency, {"clientId": c, "name": "YT Growth", "platforms": ["youtube"], "startDate": "2026-10-01", "endDate": "2026-10-31"}).json()["id"]
        a = self.post("/accounts/demo", self.agency, {"projectId": p, "platform": "instagram", "username": "@dratul.demo"}).json()["id"]
        self.assertEqual(self.post(f"/goals", self.agency, {"accountId": a, "target": 10, "days": 30}).status_code, 400)  # below current
        self.assertIn("Pehle", self.client.delete(f"{API}/clients/{c}", headers=self.agency).json()["detail"])
        self.assertEqual(self.client.delete(f"{API}/accounts/{a}", headers=self.agency).status_code, 200)
        self.assertEqual(self.client.delete(f"{API}/projects/{p}", headers=self.agency).status_code, 200)
        self.assertEqual(self.client.delete(f"{API}/clients/{c}", headers=self.agency).status_code, 200)

    def test_12_other_agency_cannot_touch_my_data(self):
        other = self.register("other@test.dev", "Other Agency")
        mine = self.get("/clients", self.agency).json()[0]["id"]
        self.assertEqual(self.client.delete(f"{API}/clients/{mine}", headers=other).status_code, 404)
        self.assertEqual(self.get("/clients", other).json(), [])

    # ---------------- roles ----------------

    def test_20_viewer_role_is_read_only(self):
        self.assertEqual(self.post("/members", self.agency, {"email": "viewer@test.dev", "role": "viewer"}).status_code, 200)
        viewer = self.register("viewer@test.dev", "ignored")
        me = self.get("/me", viewer).json()
        self.assertEqual(me["role"], "viewer")
        self.assertEqual(me["agency"]["id"], self._agency_id(self.agency))
        self.assertEqual(len(self.get("/clients", viewer).json()), 2)
        r = self.post("/clients", viewer, {"name": "Nope"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.get("/admin/stats", viewer).status_code, 403)

    # ---------------- AI ----------------

    def test_30_ai_uses_stored_data_and_counts_usage(self):
        with mock.patch("app.routers.ai.llm", return_value="• Reels are doing best") as fake:
            r = self.post("/ai/insights", self.agency, {"days": 30})
        self.assertEqual(r.json()["text"], "• Reels are doing best")
        self.assertIn("formatPerformance", fake.call_args[0][0])
        self.assertGreaterEqual(self.get("/me", self.agency).json()["aiUsed"], 1)
        with mock.patch("app.routers.ai.llm", return_value='{"hooks":["a"],"hashtags":["#x"]}'):
            out = self.post("/ai/content", self.agency, {"platform": "instagram", "topic": "Dental", "audience": "18-35", "tone": "Friendly", "language": "Hinglish"}).json()
        self.assertEqual(out["hooks"], ["a"])
        client_id = self.get("/clients", self.agency).json()[0]["id"]
        with mock.patch("app.routers.ai.llm", return_value="### Executive summary\n- good"):
            rid = self.post("/reports", self.agency, {"clientId": client_id, "type": "Monthly", "start": "2026-09-10", "end": "2026-10-09"}).json()["id"]
        rep = self.get(f"/reports/{rid}", self.agency).json()
        self.assertEqual(rep["brand"]["name"], "Sharma Digital")
        self.assertTrue(json.loads(rep["data"])["accounts"])

    # ---------------- subscription lock ----------------

    def test_40_expired_trial_is_read_only_until_paid(self):
        h = self.register("expired@test.dev", "Late Payer")
        with SessionLocal() as db:
            a = db.get(Agency, self._agency_id(h))
            a.trial_ends_at = int(time.time() * 1000) - DAY
            db.commit()
        self.assertEqual(self.get("/me", h).json()["access"]["state"], "expired")
        r = self.post("/clients", h, {"name": "Blocked"})
        self.assertEqual(r.status_code, 402)
        self.assertIn("Billing", r.json()["detail"])
        self.assertEqual(self.get("/clients", h).status_code, 200)  # data still visible
        # UPI payment → admin verifies → unlocked
        self.assertEqual(self.client.put(f"{API}/admin/settings", headers=self.owner, json={"upiId": "owner@okaxis", "payeeName": "Owner", "supportPhone": "", "trialDays": 30}).status_code, 200)
        self.assertEqual(self.post("/billing/upi", h, {"plan": "pro", "months": 1, "reference": "428615937204"}).status_code, 200)
        self.assertIn("pehle se", self.post("/billing/upi", h, {"plan": "pro", "months": 1, "reference": "428615937204"}).json()["detail"])
        stats = self.get("/admin/stats", self.owner).json()
        pay = next(p for p in stats["pendingPayments"] if p["reference"] == "428615937204")
        self.assertEqual(self.post(f"/admin/payments/{pay['id']}/verify", self.owner).status_code, 200)
        me = self.get("/me", h).json()
        self.assertEqual(me["access"]["state"], "active")
        self.assertEqual(self.post("/clients", h, {"name": "Now allowed"}).status_code, 200)

    def test_41_plan_limits(self):
        h = self.register("starter@test.dev", "Small Shop")
        self.post(f"/admin/agencies/{self._agency_id(h)}/plan", self.owner, {"plan": "free"})
        self.assertEqual(self.post("/clients", h, {"name": "One"}).status_code, 200)
        r = self.post("/clients", h, {"name": "Two"})
        self.assertIn("Upgrade", r.json()["detail"])
        self.assertIn("plan mein nahi", self.post("/ai/analyst", h, {"question": "why?"}).json()["detail"])

    # ---------------- Razorpay webhook ----------------

    def test_50_webhook_signature_activation_and_dedupe(self):
        with SessionLocal() as db:
            s = db.query(PlatformSettings).first()
            s.razorpay_webhook_secret = "whsec_test"
            db.commit()
        agency_id = self._agency_id(self.agency)
        end = int(time.time()) + 365 * 86400

        def send(event, secret="whsec_test"):
            raw = json.dumps(event).encode()
            return self.client.post(f"{API}/webhooks/razorpay", content=raw, headers={"X-Razorpay-Signature": hmac_sha256_hex(secret, raw)})

        sub = {"id": "sub_T1", "status": "active", "current_end": end, "notes": {"agencyId": agency_id, "plan": "pro", "cycle": "yearly"}}
        charged = {"event": "subscription.charged", "payload": {"subscription": {"entity": sub},
                                                                "payment": {"entity": {"id": "pay_T1", "amount": 1499000, "method": "upi", "status": "captured"}}}}
        self.assertEqual(send(charged, secret="wrong").status_code, 401)
        self.assertEqual(send(charged).status_code, 200)
        self.assertEqual(send(charged).status_code, 200)  # retried delivery
        paid = [p for p in self.get("/billing/invoices", self.agency).json() if p["reference"] == "pay_T1"]
        self.assertEqual(len(paid), 1)
        self.assertEqual(paid[0]["amount"], 14990)
        me = self.get("/me", self.agency).json()
        self.assertEqual(me["access"]["state"], "active")
        self.assertEqual(me["agency"]["billingCycle"], "yearly")
        cancel = {"event": "subscription.cancelled", "payload": {"subscription": {"entity": {**sub, "status": "cancelled", "current_end": None}}}}
        send(cancel)
        me = self.get("/me", self.agency).json()
        self.assertTrue(me["agency"]["cancelAtPeriodEnd"])
        self.assertEqual(me["access"]["state"], "active")  # paid period still runs

    # ---------------- integrations ----------------

    def test_60_shared_youtube_key_and_facebook_isolation(self):
        self.assertEqual(self.client.put(f"{API}/integrations/youtube", headers=self.owner, json={"apiKey": "AIzaOWNERKEY1234"}).status_code, 200)
        st = self.get("/integrations/status", self.agency).json()
        self.assertTrue(st["youtube"]["ready"])
        self.assertTrue(st["shared"]["youtube"])
        self.assertFalse(st["youtube"]["configured"])
        self.assertNotIn("AIzaOWNERKEY1234", json.dumps(st))
        self.assertFalse(st["meta"]["facebookReady"])
        project = self.get("/projects", self.agency).json()[0]["id"]
        r = self.post("/accounts/live", self.agency, {"projectId": project, "platform": "facebook", "handle": "SocialGrow"})
        self.assertIn("apna Meta token", r.json()["detail"])

    def test_70_cron_endpoint_requires_secret(self):
        self.assertEqual(self.client.post(f"{API}/cron/run?task=daily").status_code, 401)
        r = self.client.post(f"{API}/cron/run?task=daily", headers={"X-Cron-Secret": "cron-test"})
        self.assertEqual(r.json()["result"], "daily checks done")


if __name__ == "__main__":
    unittest.main()
