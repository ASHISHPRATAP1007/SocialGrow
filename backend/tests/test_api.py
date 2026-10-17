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
        self.assertIn("Connect with Facebook", r.json()["detail"])

    def test_61_one_time_owner_meta_setup_then_agencies_need_nothing(self):
        fake_info = {"pages": ["SocialGrow"], "igId": "17841400000000001", "igUsername": "socialgrow.ashish", "igToken": "PAGE_TOKEN_1",
                     "pageTokens": {"111": {"name": "SocialGrow", "username": "socialgrow", "token": "PAGE_TOKEN_1",
                                            "igId": "17841400000000001", "igUsername": "socialgrow.ashish"}}}
        with mock.patch("app.routers.integrations.long_lived", return_value=("LONG_USER_TOKEN", int(time.time() * 1000) + 60 * DAY)), \
             mock.patch("app.routers.integrations.discover", return_value=fake_info):
            r = self.post("/integrations/meta", self.owner, {"token": "EAAshort", "appId": "123456", "appSecret": "s3cret"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["neverExpires"])
        owner_st = self.get("/integrations/status", self.owner).json()
        self.assertTrue(owner_st["shared"]["isPlatformOwner"])
        self.assertTrue(owner_st["meta"]["neverExpires"])
        self.assertIsNone(owner_st["meta"]["expiresAt"])
        self.assertTrue(owner_st["meta"]["redirectUri"].endswith("/api/v1/integrations/meta/callback"))
        # any agency: Instagram ready + one-click Facebook available, with zero setup of their own
        st = self.get("/integrations/status", self.agency).json()
        self.assertTrue(st["meta"]["instagramReady"])
        self.assertTrue(st["meta"]["oauthAvailable"])
        self.assertIsNone(st["meta"]["redirectUri"])
        self.assertNotIn("s3cret", json.dumps(st))
        # the shared Instagram connection uses the non-expiring Page token, not the 60-day user token
        from app.services.sync_service import resolve
        with SessionLocal() as db:
            integ = resolve(db, self._agency_id(self.agency))
        self.assertEqual(integ["igToken"], "PAGE_TOKEN_1")
        self.assertIsNone(integ["igExpiresAt"])
        self.assertEqual(integ["ownPageTokens"], {})  # agency can't use the owner's Facebook pages

    def test_62_agency_one_click_facebook_oauth(self):
        url = self.get("/integrations/meta/connect-url", self.agency).json()["url"]
        self.assertIn("client_id=123456", url)
        state = url.split("state=")[1].split("&")[0]
        bad = self.client.get(f"{API}/integrations/meta/callback?code=x&state=forged", follow_redirects=False)
        self.assertIn("oauth=error", bad.headers["location"])
        agency_pages = {"pages": ["Sharma Clinic"], "igId": None, "igUsername": None, "igToken": None,
                        "pageTokens": {"222": {"name": "Sharma Clinic", "username": "sharmaclinic", "token": "PAGE_TOKEN_2", "igId": None, "igUsername": None}}}
        with mock.patch("app.routers.integrations.exchange_code", return_value="short"), \
             mock.patch("app.routers.integrations.long_lived", return_value=("LONG2", int(time.time() * 1000) + 60 * DAY)), \
             mock.patch("app.routers.integrations.discover", return_value=agency_pages):
            ok = self.client.get(f"{API}/integrations/meta/callback?code=abc&state={state}", follow_redirects=False)
        self.assertIn("/settings?oauth=connected&provider=facebook", ok.headers["location"])
        st = self.get("/integrations/status", self.agency).json()
        self.assertTrue(st["meta"]["facebookReady"])
        self.assertTrue(st["meta"]["neverExpires"])
        self.assertTrue(st["meta"]["instagramReady"])  # still shared from the owner
        from app.services.sync_service import resolve
        with SessionLocal() as db:
            self.assertIn("222", resolve(db, self._agency_id(self.agency))["ownPageTokens"])
        # viewer (not admin) cannot start the connect flow
        viewer = self.client.post(f"{API}/auth/login", json={"email": "viewer@test.dev", "password": PW}).json()["accessToken"]
        self.assertEqual(self.get("/integrations/meta/connect-url", {"Authorization": f"Bearer {viewer}"}).status_code, 403)

    def test_64_connected_pages_can_be_added_to_a_client(self):
        # pages from the earlier "Connect with Facebook" (no client chosen) wait in "available"
        avail = self.get("/accounts/available", self.agency).json()
        self.assertIn(("facebook", "222"), {(i["platform"], i["id"]) for i in avail})
        client_id = self.get("/clients", self.agency).json()[0]["id"]
        fb_data = {"externalId": "222", "username": "sharmaclinic", "displayName": "Sharma Clinic", "followers": 1500, "following": 0,
                   "posts": [{"externalId": "p1", "title": "Hello", "format": "Post", "publishedAt": "2026-10-01", "views": 0,
                              "likes": 10, "comments": 2, "shares": 1, "url": None}]}
        with mock.patch("app.services.sync_service.fetch_facebook", return_value=fb_data):
            r = self.post("/accounts/add-connected", self.agency, {"clientId": client_id, "items": [{"platform": "facebook", "id": "222"}]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["added"], [{"platform": "facebook", "username": "sharmaclinic"}])
        self.assertNotIn(("facebook", "222"), {(i["platform"], i["id"]) for i in self.get("/accounts/available", self.agency).json()})

    def test_65_client_connect_link_facebook_and_google_auto_add(self):
        # owner sets up Google once
        self.assertEqual(self.client.put(f"{API}/integrations/google-app", headers=self.agency, json={"clientId": "x", "clientSecret": "y"}).status_code, 403)
        bad = self.client.put(f"{API}/integrations/google-app", headers=self.owner, json={"clientId": "me@gmail.com", "clientSecret": "x"})
        self.assertEqual(bad.status_code, 400)
        r = self.client.put(f"{API}/integrations/google-app", headers=self.owner, json={"clientId": "goog-123.apps.googleusercontent.com", "clientSecret": "gsecret"})
        self.assertEqual(r.status_code, 200)
        owner_st = self.get("/integrations/status", self.owner).json()
        self.assertTrue(owner_st["google"]["redirectUri"].endswith("/api/v1/integrations/google/callback"))
        self.assertNotIn("gsecret", json.dumps(owner_st))
        # agency creates a link for a new client
        cid = self.post("/clients", self.agency, {"name": "Gupta Bakery"}).json()["id"]
        link = self.post(f"/clients/{cid}/connect-link", self.agency).json()["url"]
        token = link.rsplit("/", 1)[1]
        self.assertEqual(self.post(f"/clients/{cid}/connect-link", self.agency).json()["url"], link)  # same link reused
        # client opens it — no login
        info = self.client.get(f"{API}/public/connect/{token}").json()
        self.assertEqual(info["clientName"], "Gupta Bakery")
        self.assertEqual(info["providers"], {"facebook": True, "google": True})
        self.assertEqual(self.client.get(f"{API}/public/connect/nope").status_code, 404)
        # --- Facebook: page + linked Instagram both added under the client
        url = self.client.get(f"{API}/public/connect/{token}/start?provider=facebook").json()["url"]
        state = url.split("state=")[1].split("&")[0]
        pages = {"pages": ["Gupta Bakery"], "igId": "1789", "igUsername": "guptabakery", "igToken": "PT3",
                 "pageTokens": {"333": {"name": "Gupta Bakery", "username": "guptabakery", "token": "PT3", "igId": "1789", "igUsername": "guptabakery"}}}
        fb = {"externalId": "333", "username": "guptabakery", "displayName": "Gupta Bakery", "followers": 900, "following": 0, "posts": []}
        ig = {"externalId": "1789", "username": "guptabakery", "displayName": "Gupta Bakery", "followers": 4200, "following": 10, "posts": []}
        with mock.patch("app.routers.integrations.exchange_code", return_value="short"), \
             mock.patch("app.routers.integrations.long_lived", return_value=("LONG3", int(time.time() * 1000) + 60 * DAY)), \
             mock.patch("app.routers.integrations.discover", return_value=pages), \
             mock.patch("app.services.sync_service.fetch_facebook", return_value=fb), \
             mock.patch("app.services.sync_service.fetch_instagram", return_value=ig):
            res = self.client.get(f"{API}/integrations/meta/callback?code=abc&state={state}", follow_redirects=False)
        loc = res.headers["location"]
        self.assertIn(f"/connect/{token}?oauth=connected&provider=facebook", loc)
        self.assertIn("added=2", loc)
        # --- Google: YouTube channel added, synced with its own login (no API key)
        url = self.client.get(f"{API}/public/connect/{token}/start?provider=google").json()["url"]
        self.assertIn("client_id=goog-123.apps.googleusercontent.com", url)
        self.assertIn("access_type=offline", url)
        state = url.split("state=")[1].split("&")[0]
        yt = {"externalId": "UCgupta", "username": "guptabakery", "displayName": "Gupta Bakery", "followers": 120, "following": 0,
              "totalViews": 5000, "posts": []}
        with mock.patch("app.routers.integrations.exchange_code_google", return_value={"access_token": "at", "refresh_token": "rt"}), \
             mock.patch("app.routers.integrations.my_channels", return_value=[{"id": "UCgupta", "title": "Gupta Bakery", "handle": "guptabakery"}]), \
             mock.patch("app.services.sync_service.google_access_token", return_value="fresh") as gat, \
             mock.patch("app.services.sync_service.fetch_youtube", return_value=yt) as fy:
            res = self.client.get(f"{API}/integrations/google/callback?code=abc&state={state}", follow_redirects=False)
        self.assertIn("oauth=connected&provider=google", res.headers["location"])
        self.assertIn("added=1", res.headers["location"])
        gat.assert_called_with("goog-123.apps.googleusercontent.com", "gsecret", "rt")
        self.assertEqual(fy.call_args[0], ("UCgupta", "oauth:fresh"))
        accs = [a for a in self.get("/accounts", self.agency).json() if a["clientName"] == "Gupta Bakery"]
        self.assertEqual(sorted(a["platform"] for a in accs), ["facebook", "instagram", "youtube"])
        self.assertTrue(all(a["mode"] == "api" for a in accs))
        self.assertEqual(len(self.client.get(f"{API}/public/connect/{token}").json()["connected"]), 3)
        # cancel on the Google screen goes back to the link page
        url = self.client.get(f"{API}/public/connect/{token}/start?provider=google").json()["url"]
        state = url.split("state=")[1].split("&")[0]
        res = self.client.get(f"{API}/integrations/google/callback?error=access_denied&state={state}", follow_redirects=False)
        self.assertIn("oauth=cancelled", res.headers["location"])

    def test_66_account_details_show_full_history_without_date_range(self):
        acc = next(a for a in self.get("/accounts", self.agency).json() if a["username"] == "guptabakery" and a["platform"] == "youtube")
        from app.database import SessionLocal as S
        from app.models import Post as P
        with S() as db:  # a quiet channel: last video more than a year ago
            db.add(P(agency_id=self._agency_id(self.agency), account_id=acc["id"], platform="youtube", format="Video", title="Old video",
                     published_at="2025-08-13", external_id="vid1", views=1299, likes=3, comments=2, shares=0))
            db.commit()
        d = self.get(f"/accounts/{acc['id']}/details", self.agency).json()
        self.assertEqual(d["lifetime"]["posts"], 1)
        self.assertEqual(d["lifetime"]["views"], 1299)
        self.assertEqual(d["bestByViews"][0]["title"], "Old video")
        self.assertGreater(d["lifetime"]["daysSinceLastPost"], 300)
        self.assertTrue(d["commentsSupported"])
        self.assertEqual(len(self.get("/posts", self.agency, params={"days": 90, "accountId": acc["id"]}).json()), 0)
        self.assertEqual(len(self.get("/posts", self.agency, params={"days": 0, "accountId": acc["id"]}).json()), 1)
        ov = self.get("/analytics/overview", self.agency, params={"days": 30, "accountId": acc["id"]}).json()
        self.assertEqual(ov["quietAccounts"][0]["lastPostAt"], "2025-08-13")
        post_id = d["posts"][0]["id"]
        with mock.patch("app.routers.engage.google_access_token", return_value="tok"), \
             mock.patch("app.routers.engage.youtube.fetch_comments", return_value={"items": [{"id": "c1", "text": "Nice"}], "nextPageToken": None}) as fc:
            r = self.get(f"/posts/{post_id}/comments", self.agency, params={"order": "time"})
        self.assertEqual(r.json()["items"][0]["text"], "Nice")
        self.assertEqual(fc.call_args[0], ("vid1", "AIzaOWNERKEY1234", None, "time"))  # comments read with the API key
        # replying needs the comment permission — the old (read-only) Google login is refused with a clear message
        r = self.post(f"/posts/{post_id}/comments", self.agency, {"text": "Thanks!", "parentId": "c1"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("dobara jodein", r.json()["detail"])
        # after reconnecting with the new scope, replies go out as the channel
        from app.models import Integration
        with S() as db:
            row = db.query(Integration).filter(Integration.agency_id == self._agency_id(self.agency)).one()
            row.google_channels = {k: {**v, "scope": "https://www.googleapis.com/auth/youtube.force-ssl"} for k, v in row.google_channels.items()}
            db.commit()
        video = {"id": "vid1", "title": "Old video", "description": "", "publishedAt": "2025-08-13", "url": "u", "durationSeconds": 60,
                 "channelTitle": "G", "views": 1, "likes": 1, "comments": 1}
        with mock.patch("app.routers.engage.google_access_token", return_value="tok"), \
             mock.patch("app.routers.engage.youtube.post_reply", return_value={"id": "r1", "text": "Thanks!"}) as pr, \
             mock.patch("app.routers.engage.youtube.fetch_video", return_value=video):
            r = self.post(f"/posts/{post_id}/comments", self.agency, {"text": "Thanks!", "parentId": "c1"})
            self.assertEqual(r.json()["id"], "r1")
            pr.assert_called_with("c1", "Thanks!", "tok")
            d = self.get(f"/posts/{post_id}/detail", self.agency).json()
            self.assertTrue(d["canReply"])
            self.assertEqual(d["embedId"], "vid1")
        viewer = self.client.post(f"{API}/auth/login", json={"email": "viewer@test.dev", "password": PW}).json()["accessToken"]
        self.assertEqual(self.post(f"/posts/{post_id}/comments", {"Authorization": f"Bearer {viewer}"}, {"text": "x", "parentId": "c1"}).status_code, 403)

    def test_67_youtube_upload_session(self):
        acc = next(a for a in self.get("/accounts", self.agency).json() if a["username"] == "guptabakery" and a["platform"] == "youtube")
        body = {"title": "Diwali offer", "description": "d", "tags": ["diwali"], "privacy": "public", "size": 1000, "mimeType": "video/mp4"}
        self.assertFalse(self.get(f"/accounts/{acc['id']}/youtube/upload-status", self.agency).json()["canUpload"])
        r = self.post(f"/accounts/{acc['id']}/youtube/upload-session", self.agency, body)
        self.assertIn("upload permission", r.json()["detail"])
        from app.models import Integration
        with SessionLocal() as db:
            row = db.query(Integration).filter(Integration.agency_id == self._agency_id(self.agency)).one()
            row.google_channels = {k: {**v, "scope": "x https://www.googleapis.com/auth/youtube.upload"} for k, v in row.google_channels.items()}
            db.commit()
        self.assertTrue(self.get(f"/accounts/{acc['id']}/youtube/upload-status", self.agency).json()["canUpload"])
        with mock.patch("app.routers.analytics.google_access_token", return_value="tok"), \
             mock.patch("app.routers.analytics.start_upload", return_value="https://upload.example/session1") as su:
            r = self.post(f"/accounts/{acc['id']}/youtube/upload-session", self.agency, {**body, "publishAt": "2099-01-01T10:00:00+05:30"})
        self.assertEqual(r.json()["uploadUrl"], "https://upload.example/session1")
        meta = su.call_args[0][1]
        self.assertEqual(meta["status"]["privacyStatus"], "private")  # scheduled videos stay private until publishAt
        self.assertEqual(meta["status"]["publishAt"], "2099-01-01T04:30:00Z")
        self.assertEqual(su.call_args[0][2:4], (1000, "video/mp4"))
        bad = self.post(f"/accounts/{acc['id']}/youtube/upload-session", self.agency, {**body, "mimeType": "image/png"})
        self.assertEqual(bad.status_code, 400)

    def test_68_facebook_instagram_comments_reply_and_ai_suggestions(self):
        accs = {a["platform"]: a for a in self.get("/accounts", self.agency).json() if a["clientName"] == "Gupta Bakery"}
        from app.models import Post as P
        with SessionLocal() as db:
            ag = self._agency_id(self.agency)
            fb = P(agency_id=ag, account_id=accs["facebook"]["id"], platform="facebook", format="Post", title="Kaju katli",
                   published_at="2026-10-16", external_id="333_1", views=0, likes=5, comments=1, shares=0)
            ig = P(agency_id=ag, account_id=accs["instagram"]["id"], platform="instagram", format="Reel", title="Reel",
                   published_at="2026-10-16", external_id="IGM1", views=0, likes=9, comments=1, shares=0)
            db.add_all([fb, ig])
            db.commit()
            fb_id, ig_id = fb.id, ig.id
        # Facebook: detail + comments + reply use the Page's own token
        with mock.patch("app.routers.engage.meta.fb_post", return_value={"text": "Kaju katli", "publishedAt": "2026-10-16", "url": "u",
                        "media": [{"type": "image", "url": "img"}], "likes": 5, "comments": 1, "shares": 0, "views": 0}) as fp:
            d = self.get(f"/posts/{fb_id}/detail", self.agency).json()
        self.assertTrue(d["canReply"])
        self.assertEqual(fp.call_args[0], ("333_1", "PT3"))
        with mock.patch("app.routers.engage.meta.fb_write", return_value={"id": "c9", "text": "Dhanyavaad!"}) as fw:
            self.post(f"/posts/{fb_id}/comments", self.agency, {"text": "Dhanyavaad!", "parentId": "c1"})
        fw.assert_called_with("c1", "Dhanyavaad!", "PT3")
        # Instagram: reply goes to /{comment}/replies via the linked Page token
        with mock.patch("app.routers.engage.meta.ig_write", return_value={"id": "i9"}) as iw:
            self.post(f"/posts/{ig_id}/comments", self.agency, {"text": "Thank you", "parentId": "ic1"})
        iw.assert_called_with("IGM1", "ic1", "Thank you", "PT3")
        # missing permission → clear "reconnect" message
        from app.core.lib import ApiError
        with mock.patch("app.routers.engage.meta.fb_comments", side_effect=ApiError("Meta: (#10) Requires pages_read_user_content permission")):
            r = self.get(f"/posts/{fb_id}/comments", self.agency)
        self.assertIn("Connect with Facebook", r.json()["detail"])
        # AI reply suggestions in the comment's language
        with mock.patch("app.routers.engage.llm", return_value='["Bahut shukriya! 😊", "Thank you ji", "Aapka pyaar 🙏"]') as lm:
            r = self.post(f"/posts/{fb_id}/ai-reply", self.agency, {"comment": "Bahut tasty hai!", "author": "Rahul"})
        self.assertEqual(len(r.json()["options"]), 3)
        self.assertIn("SAME language", lm.call_args[0][0])

    def test_63_schema_self_updates_on_deploy(self):
        from sqlalchemy import create_engine, inspect, text
        import app.database as database
        old = create_engine(f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'old.db')}")
        with old.begin() as c:
            c.execute(text('CREATE TABLE integrations (id VARCHAR(32) PRIMARY KEY, agency_id VARCHAR(32), updated_at BIGINT)'))
        with mock.patch.object(database, "engine", old):
            database._add_missing_columns()
        cols = {c["name"] for c in inspect(old).get_columns("integrations")}
        self.assertIn("meta_page_tokens", cols)
        self.assertIn("youtube_api_key", cols)

    def test_70_cron_endpoint_requires_secret(self):
        self.assertEqual(self.client.post(f"{API}/cron/run?task=daily").status_code, 401)
        r = self.client.post(f"{API}/cron/run?task=daily", headers={"X-Cron-Secret": "cron-test"})
        self.assertEqual(r.json()["result"], "daily checks done")


if __name__ == "__main__":
    unittest.main()
