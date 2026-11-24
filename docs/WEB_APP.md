# AquaCount web app (v2): accounts, PWA and API

AquaCount's dashboard is a mobile-first Progressive Web App with sign-in. Operators
count from a phone, tablet or laptop. Every count is saved to the operator who ran it.
The app installs to the home screen and opens offline at the hatchery.

The counting pipeline (detector, tracker, line crossing, run records) is unchanged.
This upgrade adds a layer around it.

---

## 1. Architecture

```
 Phone / tablet / laptop browser
 ┌────────────────────────────────────────────────────────────────────┐
 │  web/  React + TypeScript PWA (service worker caches the app shell)│
 │  AuthProvider ─ access token in memory, refresh cookie (httpOnly)  │
 │  StationProvider ─ one Socket.IO connection: frames, counts, events│
 └───────────┬───────────────────────────────┬────────────────────────┘
   /api/auth │ (cookie)          /api/*, /socket.io (Bearer token)
             ▼                               ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │ Flask app (src/streaming/server.py)                                │
 │  ├─ src/api        guard: every /api route needs a valid token     │
 │  │   auth · me · runs/insights · admin · SPA (web/dist)            │
 │  └─ station routes upload · batch · url · camera · stop · reset    │
 │        │ job owner (thread-local)                                  │
 │        ▼                                                           │
 │  FingerlingCounter → detector → tracker → RunRecorder              │
 │        │ run saved → runs table (owner, totals)                    │
 └────────┼───────────────────────────────────────────────────────────┘
          ▼
   output/runs/<run_id>/  report.html · events.csv · crops/ · summary.json
   instance/aquacount.db  (or Postgres via DATABASE_URL)
```

**Three deployments, one codebase**

| Where | Web app served by | API | Database |
|---|---|---|---|
| Hatchery laptop (offline) | the backend, from `web/dist` | same origin | SQLite in `instance/` |
| Local development | Vite dev server (`:5173`), which proxies `/api` and `/socket.io` | `:5000` | SQLite |
| Cloud demo | Vercel (`/api/auth/*` forwarded to Render) | Render | Postgres (required) |

**One station, many operators.** The counting station still runs one job at a time.
Every signed-in operator sees the same live feed. The job remembers who started it:
others see "Bo is counting camera 0", and the run lands in Bo's history. Any operator
can stop a running count. This matches how a hatchery shares one channel camera.

---

## 2. Folder structure

```
src/api/                       authenticated web layer (Flask blueprints)
  __init__.py                  init_api(): DB, blueprints, auth guard, SPA serving
  config.py                    settings from env / .env (WebConfig)
  db.py                        SQLAlchemy models: User, RefreshToken, PasswordReset, RunRecord
  security.py                  passwords (scrypt), JWTs, Google ID-token check, rate limiter
  context.py                   sessions: create / rotate / revoke refresh-token families
  http.py                      @public, @rate_limit, @require_role, JSON errors
  routes_auth.py               /api/auth/*   sign-up, sign-in, Google, refresh, reset
  routes_me.py                 /api/me/*     profile, preferences, password, sessions
  routes_runs.py               /api/runs*, /api/insights, /api/stream-token
  routes_admin.py              /api/admin/*  users, station config
  mailer.py                    SMTP, or print to the console when not configured

web/
  index.html, vite.config.ts   PWA manifest + service worker (vite-plugin-pwa)
  public/                      icons, favicon, theme-init.js (no theme flash)
  src/
    main.tsx, App.tsx          entry, routes (lazy-loaded secondary pages)
    styles/                    design system
      tokens.css               colour roles (light + dark), type, spacing, radii, motion
      base.css                 reset, typography, focus, utilities
      components.css           buttons, fields, cards, badges, skeletons, toasts, ...
      layout.css               shell: top bar, bottom tab bar, sidebar, drawer, auth
      pages.css                page templates
    lib/                       framework-free logic
      api.ts                   fetch wrapper: bearer, retries, refresh-on-401, 429
      session.ts               single-flight refresh, cross-tab lock and broadcast
      token.ts                 in-memory access token
      upload.ts                XHR uploads with progress and cancel
      google.ts                Google Identity Services loader
      format.ts, theme.ts, types.ts, config.ts
    auth/
      AuthProvider.tsx         session state, sign-in/out, expiry handling
      guards.tsx               RequireAuth, RequireOnboarded, PublicOnly, RequireRole
    station/StationProvider.tsx  Socket.IO + live state + station actions
    components/
      layout/Shell.tsx         AppShell, TopBar, BottomNav, Sidebar, ProfileDrawer
      ui/primitives.tsx        Button, TextField, PasswordField, Segmented, Card, ...
      ui/feedback.tsx          Toasts, Dialog, ConfirmDialog
      counts.tsx, DailyChart.tsx, GoogleButton.tsx, BrandMark.tsx
    pages/                     one file per screen (see §4)
```

---

## 3. Authentication and sessions

| Piece | How |
|---|---|
| Passwords | scrypt (Werkzeug). At least 8 characters; length beats complexity. Unknown emails take as long to reject as wrong passwords. |
| Access token | HS256 JWT, 15 min, `Authorization: Bearer`. Kept **in memory only**, never in web storage. Checked against its session on every request, so sign-out takes effect at once. |
| Refresh token | 256-bit random value in an **httpOnly** cookie scoped to `/api/auth` (`SameSite=Lax`, `Secure` on HTTPS). Only its SHA-256 is stored. |
| Rotation | Each refresh issues a new token. Reusing an old one more than 30 s later is treated as theft and signs that session out everywhere. The 30 s grace covers two tabs refreshing together. |
| "Keep me signed in" | On: 30-day sliding session. Off: browser-session cookie, 24 h maximum. |
| Cross-site safety | Cookie calls (`refresh`, `logout`) require the `X-AquaCount-Client` header, which a cross-site form cannot send. |
| Google | "Continue with Google" (Google Identity Services) returns an ID token. The server checks its signature against Google's keys, the audience (`GOOGLE_CLIENT_ID`), the issuer and `email_verified`. |
| Account linking | Google **never** takes over an existing email/password account: the owner signs in with the password and connects Google from Profile. Unlinking Google needs a password first. |
| Password reset | A single-use link, valid 30 min, stored hashed. Using it signs out every session. Without SMTP the link is printed in the server window. Links are built from `APP_URL` only, never the request's Host header. |
| Roles | The first account on a station is **admin**, later ones are **operator** (or admin via `ADMIN_EMAILS`). Admins see every run and manage users. The last active admin cannot be removed. |
| Rate limits | Sign-up 10/10 min, sign-in 20/5 min per IP, 8 failed sign-ins per account per 15 min, reset requests 5/15 min, job starts 30/min per user. Answers are `429` with `Retry-After`; the app shows a countdown. |
| Files & images | Run files load with a 15-minute **media token** (`?t=`) scoped to one run, so `<img>` tags and downloads work without exposing the access token. Reports are served with a sandboxing CSP. |
| Socket.IO | The access token goes in the handshake `auth`. Refused connections refresh the token once and reconnect. |

**On the web app side**

- At startup the app silently refreshes from the cookie. If the server is asleep (Render free
  tier) it explains the wait; if it is unreachable it retries automatically.
- A token is refreshed a minute before it expires, when a sleeping tab wakes, and once
  after any `401`. If that fails, the app returns to sign-in with "Your session ended", then
  comes back to the same page afterwards.
- Signing in or out in one tab updates the others (BroadcastChannel). Refreshes are
  serialised across tabs (Web Locks), so rotation never misfires.

---

## 4. Screens

| Route | Screen |
|---|---|
| `/login`, `/signup`, `/forgot-password`, `/reset-password` | Sign-in with Google button, inline errors, rate-limit countdown, password strength |
| `/welcome` | Onboarding: name and role → hatchery, counting setup and graded classes → daily target and theme |
| `/` | Home: station status (live when counting), today vs. target, quick-launch, recent activity, pre-count checklist |
| `/count` | Live count: annotated feed (full screen), live class counters, source picker (station camera, upload with progress/cancel, photo batch, stream URL), stop/reset, last saved count, batch gallery |
| `/history`, `/history/:runId` | Search and filter by status, grouped by day; run detail with calibrated estimate, class mix, spot-check crops, report/CSV/JSON downloads, settings used |
| `/insights` | Fish per day (chart + table), class mix, best day, busiest hour, success rate; admins can switch to the whole station |
| `/profile` | Account, connected Google account, password, signed-in devices, delete account |
| `/settings` | Theme, hatchery preferences, counting defaults, install app, counting guide |
| `/admin` | Users (role, deactivate) and station configuration (model fingerprint, thresholds, calibration) |

**Navigation:** below 768 px, a top bar (page title, connection status, account drawer)
and a bottom tab bar (Home · History · **Count** · Insights · Profile) with safe-area
padding. From 768 px, a sidebar: icons only up to 1099 px, full labels from 1100 px.

**Design system:** colour roles in `tokens.css` with dark (default) and light modes,
each chosen separately rather than inverted. Class colours match the boxes on the video
(fingerling green, post-fingerling blue, juvenile orange) and were checked for
colour-vision deficiency on both themes. They always appear with names and numbers,
never colour alone. Also: 4 px spacing scale, 44 px touch targets, skeleton loaders,
empty and error states with retry, reduced-motion support, visible focus rings.

---

## 5. API

All routes need `Authorization: Bearer <token>` unless marked public.

| Method & path | Purpose |
|---|---|
| `GET /api/health` *(public)* | Liveness for Render |
| `GET /api/auth/config` *(public)* | Google client ID, sign-up allowed, reset delivery |
| `POST /api/auth/signup` *(public)* | `{name, email, password, remember}` → `201 {access_token, expires_in, user}` + cookie |
| `POST /api/auth/login` *(public)* | `{email, password, remember}` |
| `POST /api/auth/google` *(public)* | `{credential}` (Google ID token) |
| `POST /api/auth/refresh` *(public, cookie)* | New access token; rotates the cookie |
| `POST /api/auth/logout` *(public, cookie)* | Ends this session |
| `POST /api/auth/logout-all` | Ends every session |
| `POST /api/auth/forgot` *(public)* | `{email}` → always `202` |
| `POST /api/auth/reset` *(public)* | `{token, password}` |
| `POST /api/auth/google/link`, `/unlink` | Connect / disconnect Google |
| `GET/PATCH/DELETE /api/me` | Profile (+ run/fish totals), rename, delete account |
| `PATCH /api/me/preferences` | Validated keys: `theme, hatchery_name, role_title, setup_type, size_focus, daily_target, default_source, camera_index, stream_url, compact_numbers, haptics` |
| `POST /api/me/onboarding` | Preferences + name, marks onboarding done |
| `POST /api/me/password` | Change (needs current) or set; signs out other devices |
| `GET /api/me/sessions`, `DELETE /api/me/sessions/<id>` | Signed-in devices |
| `GET /api/runs` | `?scope=mine|all&status=&kind=&q=&limit=&offset=` |
| `GET /api/runs/<id>` | Detail + files + crops + `media_token` |
| `GET /api/runs/<id>/<file>` | File (bearer or `?t=`) |
| `GET /api/insights` | `?days=14&tz_offset=<minutes>&scope=` |
| `GET /api/stream-token` | Media token for `/video_feed?t=` |
| `GET /api/admin/users`, `PATCH /api/admin/users/<id>` | `{role, is_active}` |
| `GET /api/admin/station` | Model, thresholds, calibration, features |

Errors are `{"error": "<message for people>", "code": "<machine code>", "field"?: "...", "retry_after"?: N}`.
Station routes (`/api/upload`, `/api/upload_batch`, `/api/process_url`, `/api/start_camera`,
`/api/stop`, `/api/reset_counts`, `/api/status`) are unchanged apart from needing sign-in.
See the README.

---

## 6. Running it

**Local development**

```bash
pip install -r requirements.txt              # or requirements-prod.txt
python main.py --web-server --no-display --weights models/best.onnx --port 5000
cd web && npm ci && npm run dev              # http://localhost:5173
```

The first account you create becomes the station admin. Reset links appear in the
backend console.

**Hatchery laptop:** `run_hatchery.bat` now installs new Python packages whenever
`requirements-prod.txt` changes, and builds the web app on first run. That build needs
Node.js LTS and internet once; alternatively, copy a built `web/dist` folder over.
Optional settings, such as a Google client ID, go in a `.env` file at the repo root
(see `.env.example`). Phones on the hatchery Wi-Fi open the printed LAN address.
Email/password works fully offline. Google sign-in needs internet, and Google only
accepts sign-ins from registered `https://` or `localhost` addresses. Phones using
`http://192.168.x.x` should therefore sign in with email and password; Google works
on the laptop itself (`localhost`).

> Service workers only run on `https://` or `localhost`. On a LAN address
> (`http://192.168.x.x:5000`) the app works fully, but phones will not install it or
> cache it offline. For that, serve it over HTTPS (for example a local reverse proxy
> with a certificate).

**Demo mode (no server, no database)**

`npm run dev:demo` or `npm run build:demo` runs the whole app in the browser: a
simulated station (synthetic fish crossing the line, in the real overlay's style),
sample history, and a demo account (`demo@aquacount.app` / `fingerlings`). Nothing is
sent anywhere, and a banner says so on every screen. Vercel **preview** deployments
(any branch other than production) build in demo mode automatically when
`VITE_API_URL` is not set, so every branch gets a clickable preview. Production
builds never fall back to demo mode. The demo code (`web/src/demo/`) is loaded only in
demo builds; normal builds do not contain it.

**Cloud (Render + Vercel)**

1. **Database:** create a free Postgres (Neon, Supabase or Render Postgres). Put its
   URL in Render's `DATABASE_URL`. Without it, accounts disappear whenever the free
   service restarts.
2. **Render:** deploy with `render.yaml`. `JWT_SECRET` is generated for you. Set
   `APP_URL` and `CORS_ORIGINS` to the Vercel address.
3. **Vercel:** set `VITE_API_URL` to the Render URL and deploy. If your Render service
   name differs, edit `vercel.json` (the `/api/auth` rewrite and the CSP).
4. **Google sign-in (optional):** Google Cloud Console → APIs & Services → Credentials
   → *Create OAuth client ID* → *Web application*. Under **Authorised JavaScript origins**,
   add `https://<your-app>.vercel.app` and `http://localhost:5173` (plus
   `http://localhost:5000` for the laptop). No redirect URI is needed. Put the client
   ID in Render's `GOOGLE_CLIENT_ID`; the button then appears on its own.
5. **Email (optional):** set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`,
   `SMTP_FROM`.

Run files (`output/runs`) on Render's free tier are still wiped on restart. History
rows survive in Postgres, and the app says when a run's files are gone. The hatchery
laptop keeps everything.

---

## 7. Tests

```bash
python -m unittest discover -s tests          # 60 backend tests (33 for src/api)
cd web && npm test                             # API client + formatting (vitest)
cd web && npm run build                        # strict type-check + production build
```

`tests/test_api.py` covers sign-up/sign-in, lockout and rate limits, refresh rotation,
theft detection and the grace window, sign-out, sessions, password change and reset,
Google sign-in/linking (with a stand-in verifier), per-user run isolation, media-token
scope, path traversal, admin rules, Socket.IO sign-in and SPA serving.

---

## 8. Known limits and next steps

- **Migrations:** tables are created on start-up. Adding columns later needs Alembic
  (or a one-off `ALTER TABLE`).
- **Rate limiter is in memory:** correct for one worker (Render config, hatchery laptop).
  Use Redis-backed limits if you scale out.
- **No invitations yet:** with `ALLOW_SIGNUP=0`, only existing accounts can sign in.
  An admin "invite by email" flow is the natural next step.
- **Email addresses are not verified at sign-up.** Google accounts are verified by
  Google, and password reset proves ownership.
- **One shared station:** the live feed and counters are shared by every signed-in user,
  as before. Supporting several cameras would need one pipeline per camera.
- **No AI chat:** the brief listed an assistant view as an example; the project has no
  such feature today, so none was invented.
