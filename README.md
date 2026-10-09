# SocialGrow AI

Social media analytics, AI insights aur agency SaaS — **Next.js (JavaScript) + Tailwind CSS** frontend aur **Python FastAPI + PostgreSQL** backend.

```
socialgrow/
├── frontend/   Next.js 15 (App Router, JavaScript), Tailwind CSS v4, Axios, SWR, Recharts
├── backend/    FastAPI, SQLAlchemy 2, PostgreSQL (local: SQLite), JWT auth
└── render.yaml Render par backend ka free deploy blueprint
```

## Features

| Phase | Features |
|---|---|
| 1 — Build | Login / Register / Forgot password, Dashboard, Clients → Projects → Social Accounts, Profile Analytics (7d–1y), Post Analytics, Growth Goals, AI Insight |
| 2 — Grow | Team roles (Owner, Admin, Manager, Analyst, Content Manager, Viewer), Campaigns, AI Growth Analyst, AI Content Assistant, AI Content Calendar, AI Client Reports (PDF), Notifications |
| 3 — Monetize | 30-din free trial (signup par automatic), Starter / Pro / Agency plans (monthly + yearly), Razorpay auto-renew, UPI fallback, read-only lock, White label, Admin Panel (MRR, agencies, payments) |
| Real data | YouTube (Data API v3), Instagram (Graph API — Business Discovery), Facebook Pages (Graph API), har 6 ghante auto-sync |

**Pehla registered user = platform owner (Admin Panel).** Baaki sab users agencies hain jinko signup par turant 30 din ka Pro trial milta hai.

---

## 1. Apne computer par chalana (Windows / Mac / Linux)

Zaroori: **Python 3.11+** aur **Node.js 20+**.

### Backend

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate      Mac/Linux:  source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env        # Mac/Linux: cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

- `DATABASE_URL` khaali chhodo → local `socialgrow.db` (SQLite) file ban jayegi.
- API docs: http://localhost:8000/docs
- Tests: `pytest -q` (14 tests)

### Frontend

```bash
cd frontend
npm install
copy .env.example .env.local  # Mac/Linux: cp .env.example .env.local
npm run dev
```

Browser: http://localhost:3000 → **"Naya account"** se pehla account banao (ye Admin ban jayega).

---

## 2. Free mein live karna (permanent link)

| Kya | Kahan | Free plan |
|---|---|---|
| Database | **Neon** (neon.tech) — PostgreSQL | 0.5 GB |
| Backend | **Render** (render.com) — FastAPI | 750 ghante/mahina (15 min idle par so jata hai) |
| Frontend | **Vercel** (vercel.com) — Next.js | Hobby |
| AI | **Google AI Studio** — Gemini API key | Free tier |
| Cron | **cron-job.org** — backend ko jagaye rakhna + jobs | Free |

### Step A — Code GitHub par
GitHub par naya repo banao (jaise `socialgrow-ai`) aur ye poora folder push karo.

### Step B — Neon database
1. neon.tech → Sign up → **New Project** (region: Singapore / Mumbai ke paas wala).
2. **Connection string** copy karo (`postgresql://...`). Ye `DATABASE_URL` hai.

### Step C — Gemini AI key
aistudio.google.com/apikey → **Create API key** → copy.

### Step D — Render backend
1. render.com → Sign up (GitHub se) → **New → Blueprint** → apna repo chuno (`render.yaml` apne aap padha jayega).
2. Env vars bharo:
   - `DATABASE_URL` = Neon wala URL
   - `GEMINI_API_KEY` = Step C wali key
   - `CORS_ORIGINS` = abhi `*` mat daalo — Step E ke baad Vercel URL daalna (jaise `https://socialgrow.vercel.app`)
   - `PUBLIC_API_URL` = Render ka URL (jaise `https://socialgrow-api.onrender.com`)
3. Deploy hone ke baad check: `https://<render-url>/api/v1/health` → `{"status":"ok"}`

### Step E — Vercel frontend
1. vercel.com → **Add New → Project** → repo chuno → **Root Directory: `frontend`**.
2. Environment Variable: `NEXT_PUBLIC_API_URL` = Render backend URL (bina `/` ke end mein).
3. **Deploy** → aapka permanent link: `https://<name>.vercel.app`
4. Render par wapas jao → `CORS_ORIGINS` mein ye Vercel URL daalo → save (redeploy hoga).

### Step F — Pehla login
Vercel link kholo → **Naya account** → aapka account **platform owner** banega → **Admin Panel** dikhega.

### Step G — Background jobs (free)
Render free plan idle hone par so jata hai, isliye cron-job.org par 2 jobs banao:
- **Har 6 ghante:** `POST https://<render-url>/api/v1/cron/run?task=sync`
- **Roz subah 9 baje:** `POST https://<render-url>/api/v1/cron/run?task=daily`
- Dono mein header: `X-Cron-Secret: <Render ka CRON_SECRET>` (Render → Environment mein dikhega)

---

## 3. Real data aur payments jodna (app ke andar se)

Sab kuch app ke **Settings** aur **Admin Panel** se hota hai — code badalne ki zarurat nahi.

1. **YouTube** — Owner account → Settings → Integrations → YouTube API key (Google Cloud se free). Ye key **saari agencies ke liye** kaam karti hai.
2. **Instagram** — Owner account → Settings → Meta: App ID + App Secret + User Access Token (60 din valid, expiry se pehle reminder). Saari agencies kisi bhi Business/Creator Instagram ko jod sakti hain.
3. **Facebook Pages** — har agency apna khud ka Meta token jodti hai (security: koi doosre ka Page nahi padh sakta).
4. **Razorpay (auto-renew)** — Admin Panel → Razorpay: Key ID, Key Secret, Webhook Secret. Webhook URL wahi dikhta hai — use Razorpay Dashboard → Settings → Webhooks mein daalo (events: `subscription.*`). Pehle **Test mode** keys se try karo.
5. **UPI fallback** — Razorpay set hone tak Admin Panel mein apni UPI ID daalo; agencies QR se pay karke UTR daalengi, aap verify karoge.

## 4. Security notes

- Passwords PBKDF2-SHA256 (240k iterations) se hash hote hain; login JWT (7 din).
- API keys / tokens sirf backend database mein — frontend ko kabhi wapas nahi bheje jaate.
- Razorpay webhook HMAC-SHA256 signature verify karta hai; ek payment do baar record nahi hota.
- Har agency ka data alag (multi-tenant) — har API call agency check karti hai.
- Production mein `JWT_SECRET` zaroor lamba random rakho (Render blueprint apne aap banata hai).
