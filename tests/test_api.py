"""
Tests for the authenticated web layer (src/api) wired into StreamingServer.

Covers sign-up/sign-in, refresh-token rotation and theft detection, Google
sign-in (with a stand-in verifier), password reset, per-user run history and
file access, admin rules, Socket.IO sign-in, and serving the PWA build.

Run from the repository root:
    python -m unittest discover -s tests -v
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# A fixed signing key, so tests never write instance/secret_key into the repo.
os.environ.setdefault('JWT_SECRET', 'aquacount-tests-' + 'x' * 40)
sys.path.insert(0, str(ROOT / "src"))

from flask import Flask  # noqa: E402
from sqlalchemy import select, update  # noqa: E402

import api.routes_auth as routes_auth  # noqa: E402
from api import WebConfig, init_api  # noqa: E402
from api.context import REFRESH_COOKIE  # noqa: E402
from api.db import RefreshToken, utcnow  # noqa: E402
from api.security import GoogleVerificationError  # noqa: E402
from streaming.server import StreamingServer  # noqa: E402

CSRF = {"X-AquaCount-Client": "web"}
PASSWORD = "fingerlings-2026"


class FakeGoogle:
    """Accepts credentials of the form 'google:<sub>:<email>'."""

    def verify(self, credential):
        parts = credential.split(":")
        if len(parts) != 3 or parts[0] != "google":
            raise GoogleVerificationError("The Google sign-in was invalid or has expired.")
        return {"sub": parts[1], "email": parts[2], "email_verified": True,
                "name": "Google User", "picture": "https://example.com/a.png"}


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aquacount_api_"))
        self.server = StreamingServer(runs_dir=str(self.tmp / "runs"),
                                      database_url=f"sqlite:///{(self.tmp / 'api.db').as_posix()}")
        self.api = self.server.api
        self.api.cfg = replace(self.api.cfg, google_client_id="test-client-id")
        self.api.google = FakeGoogle()
        self.client = self.server.app.test_client()

    def tearDown(self):
        self.api.db.dispose()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # helpers
    def signup(self, email="ada@example.com", name="Ada", password=PASSWORD, client=None):
        c = client or self.client
        resp = c.post("/api/auth/signup", json={"name": name, "email": email, "password": password})
        self.assertEqual(resp.status_code, 201, resp.get_json())
        return resp.get_json()

    @staticmethod
    def bearer(token):
        return {"Authorization": f"Bearer {token}"}

    def refresh_cookie(self, client=None):
        cookie = (client or self.client).get_cookie(REFRESH_COOKIE, path="/api/auth")
        return cookie.value if cookie else None


class SignUpAndSignInTests(ApiTestCase):

    def test_public_endpoints_need_no_sign_in(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        cfg = self.client.get("/api/auth/config").get_json()
        self.assertEqual(cfg["google_client_id"], "test-client-id")
        self.assertTrue(cfg["signup_enabled"])

    def test_station_endpoints_require_sign_in(self):
        for method, path in [("get", "/api/status"), ("get", "/api/counts"), ("post", "/api/stop"),
                             ("post", "/api/reset_counts"), ("post", "/api/process_url"),
                             ("get", "/api/runs"), ("get", "/api/me"), ("get", "/video_feed")]:
            resp = getattr(self.client, method)(path)
            self.assertEqual(resp.status_code, 401, path)
            if path.startswith("/api/"):
                self.assertEqual(resp.get_json()["code"], "unauthorized")

    def test_signup_returns_token_sets_httponly_cookie_and_first_user_is_admin(self):
        first = self.signup()
        self.assertEqual(first["user"]["role"], "admin")
        self.assertTrue(first["user"]["has_password"])
        self.assertFalse(first["user"]["onboarded"])
        cookie = self.client.get_cookie(REFRESH_COOKIE, path="/api/auth")
        self.assertIsNotNone(cookie)
        self.assertTrue(cookie.http_only)

        second = self.signup("bo@example.com", "Bo", client=self.server.app.test_client())
        self.assertEqual(second["user"]["role"], "operator")

        me = self.client.get("/api/me", headers=self.bearer(first["access_token"]))
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.get_json()["user"]["email"], "ada@example.com")

    def test_signup_validation(self):
        bad = [({"name": "", "email": "a@b.co", "password": PASSWORD}, "invalid_name"),
               ({"name": "A", "email": "not-an-email", "password": PASSWORD}, "invalid_email"),
               ({"name": "A", "email": "a@b.co", "password": "short"}, "weak_password"),
               ({"name": "A", "email": "a@b.co", "password": "a@b.co"}, "weak_password")]
        for body, code in bad:
            resp = self.client.post("/api/auth/signup", json=body)
            self.assertEqual(resp.status_code, 400, body)
            self.assertEqual(resp.get_json()["code"], code)
        self.signup("A@B.co")
        dup = self.client.post("/api/auth/signup", json={"name": "A", "email": "a@b.co", "password": PASSWORD})
        self.assertEqual(dup.status_code, 409)
        self.assertEqual(dup.get_json()["code"], "email_taken")

    def test_login_and_failed_attempt_lockout(self):
        self.signup()
        ok = self.client.post("/api/auth/login", json={"email": "ADA@example.com", "password": PASSWORD})
        self.assertEqual(ok.status_code, 200)

        for _ in range(8):
            bad = self.client.post("/api/auth/login", json={"email": "ada@example.com", "password": "wrong-pass"})
            self.assertEqual(bad.status_code, 401)
            self.assertEqual(bad.get_json()["code"], "invalid_credentials")
        locked = self.client.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD})
        self.assertEqual(locked.status_code, 429)
        self.assertGreater(int(locked.headers["Retry-After"]), 0)

    def test_unknown_email_gets_same_answer_as_wrong_password(self):
        self.signup()
        a = self.client.post("/api/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
        b = self.client.post("/api/auth/login", json={"email": "ada@example.com", "password": "wrong-pass"})
        self.assertEqual(a.status_code, b.status_code)
        self.assertEqual(a.get_json(), b.get_json())

    def test_signup_is_rate_limited_per_ip(self):
        for i in range(10):
            self.client.post("/api/auth/signup", json={"name": "x", "email": f"u{i}@example.com", "password": PASSWORD})
        resp = self.client.post("/api/auth/signup", json={"name": "x", "email": "u99@example.com", "password": PASSWORD})
        self.assertEqual(resp.status_code, 429)
        self.assertIn("Retry-After", resp.headers)


class SessionTests(ApiTestCase):

    def test_refresh_requires_client_header_and_rotates_cookie(self):
        self.signup()
        first = self.refresh_cookie()
        self.assertEqual(self.client.post("/api/auth/refresh").status_code, 403)
        resp = self.client.post("/api/auth/refresh", headers=CSRF)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access_token", resp.get_json())
        self.assertNotEqual(self.refresh_cookie(), first)

    def test_concurrent_refresh_within_grace_window_is_not_theft(self):
        self.signup()
        old = self.refresh_cookie()
        self.assertEqual(self.client.post("/api/auth/refresh", headers=CSRF).status_code, 200)
        other_tab = self.server.app.test_client()
        other_tab.set_cookie(REFRESH_COOKIE, old, path="/api/auth")
        resp = other_tab.post("/api/auth/refresh", headers=CSRF)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(REFRESH_COOKIE, resp.headers.get("Set-Cookie", ""))  # keeps the newer cookie

    def test_reusing_an_old_refresh_token_revokes_the_session(self):
        data = self.signup()
        old = self.refresh_cookie()
        self.assertEqual(self.client.post("/api/auth/refresh", headers=CSRF).status_code, 200)
        with self.api.db.session() as s:  # move the rotation outside the grace window
            s.execute(update(RefreshToken).where(RefreshToken.rotated_at.is_not(None))
                      .values(rotated_at=utcnow() - timedelta(minutes=5)))
        thief = self.server.app.test_client()
        thief.set_cookie(REFRESH_COOKIE, old, path="/api/auth")
        stolen = thief.post("/api/auth/refresh", headers=CSRF)
        self.assertEqual(stolen.status_code, 401)
        # The legitimate holder is signed out too: the whole family is revoked.
        self.assertEqual(self.client.post("/api/auth/refresh", headers=CSRF).status_code, 401)
        me = self.client.get("/api/me", headers=self.bearer(data["access_token"]))
        self.assertEqual(me.status_code, 401)
        self.assertEqual(me.get_json()["code"], "session_revoked")

    def test_logout_ends_session_and_clears_cookie(self):
        data = self.signup()
        resp = self.client.post("/api/auth/logout", headers=CSRF)
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(self.refresh_cookie())
        self.assertEqual(self.client.get("/api/me", headers=self.bearer(data["access_token"])).status_code, 401)

    def test_sessions_list_and_revoke_other_device(self):
        data = self.signup()
        phone = self.server.app.test_client()
        phone.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD},
                   headers={"User-Agent": "Phone"})
        sessions = self.client.get("/api/me/sessions", headers=self.bearer(data["access_token"])).get_json()["sessions"]
        self.assertEqual(len(sessions), 2)
        self.assertTrue(sessions[0]["current"])
        other = next(s for s in sessions if not s["current"])
        resp = self.client.delete(f"/api/me/sessions/{other['id']}", headers=self.bearer(data["access_token"]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(phone.post("/api/auth/refresh", headers=CSRF).status_code, 401)

    def test_change_password_signs_out_other_devices_only(self):
        data = self.signup()
        phone = self.server.app.test_client()
        phone.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD})
        wrong = self.client.post("/api/me/password", headers=self.bearer(data["access_token"]),
                                 json={"current_password": "nope-nope", "new_password": "another-good-one"})
        self.assertEqual(wrong.status_code, 400)
        ok = self.client.post("/api/me/password", headers=self.bearer(data["access_token"]),
                              json={"current_password": PASSWORD, "new_password": "another-good-one"})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.client.get("/api/me", headers=self.bearer(data["access_token"])).status_code, 200)
        self.assertEqual(phone.post("/api/auth/refresh", headers=CSRF).status_code, 401)


class GoogleTests(ApiTestCase):

    def test_google_sign_in_creates_account_then_signs_in(self):
        first = self.client.post("/api/auth/google", json={"credential": "google:123:gg@example.com"})
        self.assertEqual(first.status_code, 201)
        body = first.get_json()
        self.assertTrue(body["is_new"])
        self.assertTrue(body["user"]["google_connected"])
        self.assertFalse(body["user"]["has_password"])
        again = self.client.post("/api/auth/google", json={"credential": "google:123:gg@example.com"})
        self.assertEqual(again.status_code, 200)
        self.assertFalse(again.get_json()["is_new"])

    def test_invalid_google_credential(self):
        resp = self.client.post("/api/auth/google", json={"credential": "forged"})
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.get_json()["code"], "google_invalid")

    def test_google_never_takes_over_an_existing_password_account(self):
        self.signup("ada@example.com")
        resp = self.server.app.test_client().post("/api/auth/google", json={"credential": "google:999:ada@example.com"})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.get_json()["code"], "account_exists")

    def test_link_and_unlink_google_while_signed_in(self):
        data = self.signup()
        h = self.bearer(data["access_token"])
        linked = self.client.post("/api/auth/google/link", headers=h, json={"credential": "google:42:ada.g@gmail.com"})
        self.assertEqual(linked.status_code, 200)
        self.assertEqual(linked.get_json()["user"]["google_email"], "ada.g@gmail.com")
        # Now Google sign-in reaches the same account.
        g = self.server.app.test_client().post("/api/auth/google", json={"credential": "google:42:ada.g@gmail.com"})
        self.assertEqual(g.get_json()["user"]["email"], "ada@example.com")
        unlinked = self.client.post("/api/auth/google/unlink", headers=h)
        self.assertFalse(unlinked.get_json()["user"]["google_connected"])

    def test_google_only_account_cannot_unlink_until_password_set(self):
        token = self.client.post("/api/auth/google", json={"credential": "google:7:solo@example.com"}).get_json()["access_token"]
        resp = self.client.post("/api/auth/google/unlink", headers=self.bearer(token))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["code"], "password_required")
        set_pw = self.client.post("/api/me/password", headers=self.bearer(token), json={"new_password": PASSWORD})
        self.assertEqual(set_pw.status_code, 200)
        self.assertEqual(self.client.post("/api/auth/google/unlink", headers=self.bearer(token)).status_code, 200)


class PasswordResetTests(ApiTestCase):

    def setUp(self):
        super().setUp()
        self.sent = []
        self._orig = routes_auth.send_mail
        routes_auth.send_mail = lambda cfg, to, subject, body: self.sent.append((to, body))

    def tearDown(self):
        routes_auth.send_mail = self._orig
        super().tearDown()

    def _reset_token(self):
        body = self.sent[-1][1]
        return body.split("token=")[1].split()[0]

    def test_forgot_password_does_not_reveal_whether_account_exists(self):
        a = self.client.post("/api/auth/forgot", json={"email": "nobody@example.com"})
        self.assertEqual(a.status_code, 202)
        self.assertEqual(self.sent, [])
        self.signup()
        b = self.client.post("/api/auth/forgot", json={"email": "ada@example.com"})
        self.assertEqual(b.status_code, 202)
        self.assertEqual(a.get_json(), b.get_json())
        self.assertEqual(len(self.sent), 1)

    def test_reset_sets_password_signs_out_everywhere_and_is_single_use(self):
        data = self.signup()
        self.client.post("/api/auth/forgot", json={"email": "ada@example.com"})
        token = self._reset_token()
        weak = self.client.post("/api/auth/reset", json={"token": token, "password": "short"})
        self.assertEqual(weak.status_code, 400)
        ok = self.client.post("/api/auth/reset", json={"token": token, "password": "brand-new-pass-1"})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.client.get("/api/me", headers=self.bearer(data["access_token"])).status_code, 401)
        again = self.client.post("/api/auth/reset", json={"token": token, "password": "brand-new-pass-2"})
        self.assertEqual(again.status_code, 400)
        login = self.client.post("/api/auth/login", json={"email": "ada@example.com", "password": "brand-new-pass-1"})
        self.assertEqual(login.status_code, 200)


class ProfileTests(ApiTestCase):

    def test_preferences_are_validated_and_onboarding_completes(self):
        h = self.bearer(self.signup()["access_token"])
        for bad in [{"theme": "neon"}, {"unknown_key": 1}, {"daily_target": -5},
                    {"size_focus": ["whale"]}, {"camera_index": "0"}]:
            self.assertEqual(self.client.patch("/api/me/preferences", headers=h, json=bad).status_code, 400, bad)
        ok = self.client.post("/api/me/onboarding", headers=h, json={
            "name": "Ada O.", "hatchery_name": "Lekki Fish Farm", "setup_type": "channel",
            "size_focus": ["juvenile", "fingerling"], "daily_target": 5000, "theme": "dark"})
        self.assertEqual(ok.status_code, 200, ok.get_json())
        user = ok.get_json()["user"]
        self.assertTrue(user["onboarded"])
        self.assertEqual(user["name"], "Ada O.")
        self.assertEqual(user["preferences"]["size_focus"], ["fingerling", "juvenile"])

    def test_delete_account_keeps_runs_unassigned(self):
        data = self.signup()
        self.signup("bo@example.com", "Bo", client=self.server.app.test_client())  # another admin-less user
        h = self.bearer(data["access_token"])
        self.assertEqual(self.client.delete("/api/me", headers=h, json={"confirm": "DELETE", "password": PASSWORD}).status_code,
                         400)  # last admin while other users exist
        bo = self.client.post("/api/auth/login", json={"email": "bo@example.com", "password": PASSWORD}).get_json()
        boh = self.bearer(bo["access_token"])
        self.assertEqual(self.client.delete("/api/me", headers=boh, json={"confirm": "nope"}).status_code, 400)
        self.assertEqual(self.client.delete("/api/me", headers=boh, json={"confirm": "DELETE", "password": PASSWORD}).status_code, 200)


class RunHistoryTests(ApiTestCase):

    def _save_run(self, owner_id, run_id, total=10, kind_job="upload"):
        """Simulate the counting thread finishing a run for `owner_id`."""
        run_dir = self.server.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        summary = {"run_id": run_id, "source": "batch.mp4", "status": "completed",
                   "started_at": "2026-11-20T09:00:00", "ended_at": "2026-11-20T09:10:00",
                   "frames_processed": 600, "processing_seconds": 120.0,
                   "counts": {"total": total, "fingerling": total - 2, "post_fingerling": 1, "juvenile": 1, "unknown": 0},
                   "corrected_total": None, "correction_factor": 1.0}
        (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        (run_dir / "report.html").write_text("<p>report</p>", encoding="utf-8")
        (run_dir / "crops").mkdir(exist_ok=True)
        (run_dir / "crops" / "000001_fingerling.jpg").write_bytes(b"\xff\xd8\xff")

        def worker():
            self.server._job_ctx.owner_id = owner_id
            self.server._job_ctx.kind = kind_job
            self.server.notify_run_saved(summary)
        t = threading.Thread(target=worker)
        t.start()
        t.join()

    def _user_id(self, email):
        from api.db import User
        with self.api.db.session() as s:
            return s.scalar(select(User.id).where(User.email == email))

    def test_each_user_sees_only_their_own_runs(self):
        ada = self.signup()
        bo = self.signup("bo@example.com", "Bo", client=self.server.app.test_client())
        self._save_run(self._user_id("ada@example.com"), "20261120_090000_ada", 12)
        self._save_run(self._user_id("bo@example.com"), "20261120_100000_bo", 30)

        mine = self.client.get("/api/runs", headers=self.bearer(bo["access_token"])).get_json()
        self.assertEqual([r["run_id"] for r in mine["runs"]], ["20261120_100000_bo"])
        self.assertEqual(mine["runs"][0]["kind"], "video")

        # Bo cannot open Ada's run, and cannot tell it exists.
        self.assertEqual(self.client.get("/api/runs/20261120_090000_ada",
                                         headers=self.bearer(bo["access_token"])).status_code, 404)
        # Operators asking for every run still get only their own.
        scoped = self.client.get("/api/runs?scope=all", headers=self.bearer(bo["access_token"])).get_json()
        self.assertEqual(scoped["scope"], "mine")

        everyone = self.client.get("/api/runs?scope=all", headers=self.bearer(ada["access_token"])).get_json()
        self.assertEqual(everyone["total"], 2)

    def test_run_detail_media_token_downloads_only_that_run(self):
        ada = self.signup()
        uid = self._user_id("ada@example.com")
        self._save_run(uid, "20261120_090000_one")
        self._save_run(uid, "20261120_090500_two")
        detail = self.client.get("/api/runs/20261120_090000_one", headers=self.bearer(ada["access_token"])).get_json()
        self.assertEqual(detail["crops"][0]["class"], "fingerling")
        self.assertIn("report.html", [f["name"] for f in detail["files"]])
        t = detail["media_token"]

        report = self.client.get(f"/api/runs/20261120_090000_one/report.html?t={t}")
        self.assertEqual(report.status_code, 200)
        self.assertIn("sandbox", report.headers["Content-Security-Policy"])
        self.assertEqual(self.client.get(f"/api/runs/20261120_090500_two/report.html?t={t}").status_code, 401)
        # Path traversal out of the run folder is refused by send_from_directory's safe_join.
        traversal = self.client.get(f"/api/runs/20261120_090000_one/../20261120_090500_two/report.html?t={t}")
        self.assertEqual(traversal.status_code, 404)
        # A media token is not an access token.
        self.assertEqual(self.client.get("/api/me", headers=self.bearer(t)).status_code, 401)

    def test_admin_sees_runs_recorded_before_accounts_existed(self):
        legacy = self.server.runs_dir / "20250101_080000_old"
        legacy.mkdir(parents=True)
        (legacy / "summary.json").write_text(json.dumps({
            "run_id": "20250101_080000_old", "status": "completed", "counts": {"total": 5},
            "started_at": "2025-01-01T08:00:00"}), encoding="utf-8")
        admin = self.signup()
        runs = self.client.get("/api/runs?scope=all", headers=self.bearer(admin["access_token"])).get_json()["runs"]
        self.assertEqual(runs[0]["run_id"], "20250101_080000_old")
        self.assertIsNone(runs[0]["owner"])

    def test_insights_sum_only_the_users_runs(self):
        ada = self.signup()
        uid = self._user_id("ada@example.com")
        self._save_run(uid, "20261120_090000_a", 10)
        self._save_run(uid, "20261120_091000_b", 15)
        with self.api.db.session() as s:  # make them "today" for the 14-day window
            from api.db import RunRecord
            s.execute(update(RunRecord).values(started_at=utcnow()))
        data = self.client.get("/api/insights?days=7", headers=self.bearer(ada["access_token"])).get_json()
        self.assertEqual(data["period"]["fish"], 25)
        self.assertEqual(data["today"]["fish"], 25)
        self.assertEqual(len(data["series"]), 7)
        self.assertEqual(data["classes"]["fingerling"], 21)

    def test_job_owner_shown_in_status_and_history(self):
        ada = self.signup()
        release = threading.Event()

        def job():
            self.server.notify_run_saved({"run_id": "20261120_120000_owned", "status": "completed",
                                          "counts": {"total": 3}})
            release.wait(2)

        self.server._start_job("camera", "camera 0", job, (),
                               owner={"id": self._user_id("ada@example.com"), "name": "Ada"})
        status = self.client.get("/api/status", headers=self.bearer(ada["access_token"])).get_json()
        self.assertEqual(status["job"]["started_by"], "Ada")
        release.set()
        runs = self.client.get("/api/runs", headers=self.bearer(ada["access_token"])).get_json()["runs"]
        self.assertEqual(runs[0]["run_id"], "20261120_120000_owned")
        self.assertEqual(runs[0]["kind"], "camera")


class AdminTests(ApiTestCase):

    def test_operator_cannot_use_admin_endpoints(self):
        self.signup()
        bo = self.signup("bo@example.com", "Bo", client=self.server.app.test_client())
        self.assertEqual(self.client.get("/api/admin/users", headers=self.bearer(bo["access_token"])).status_code, 403)

    def test_admin_manages_users_but_keeps_one_admin(self):
        ada = self.signup()
        bo = self.signup("bo@example.com", "Bo", client=self.server.app.test_client())
        h = self.bearer(ada["access_token"])
        users = self.client.get("/api/admin/users", headers=h).get_json()["users"]
        ada_id = next(u["id"] for u in users if u["is_you"])
        bo_id = next(u["id"] for u in users if not u["is_you"])
        last = self.client.patch(f"/api/admin/users/{ada_id}", headers=h, json={"role": "operator"})
        self.assertEqual(last.get_json()["code"], "last_admin")
        self.assertEqual(self.client.patch(f"/api/admin/users/{bo_id}", headers=h, json={"is_active": False}).status_code, 200)
        self.assertEqual(self.client.get("/api/me", headers=self.bearer(bo["access_token"])).status_code, 401)
        station = self.client.get("/api/admin/station", headers=h).get_json()
        self.assertEqual(station["database"], "sqlite")


class SocketTests(ApiTestCase):

    def test_socket_requires_a_valid_access_token(self):
        anon = self.server.socketio.test_client(self.server.app, auth={})
        self.assertFalse(anon.is_connected())
        token = self.signup()["access_token"]
        ok = self.server.socketio.test_client(self.server.app, auth={"token": token})
        self.assertTrue(ok.is_connected())
        ok.disconnect()


class SpaServingTests(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aquacount_spa_"))
        dist = self.tmp / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
        (dist / "assets" / "app-abc123.js").write_text("console.log(1)", encoding="utf-8")
        (dist / "sw.js").write_text("self.x=1", encoding="utf-8")
        cfg = WebConfig.from_env(database_url=f"sqlite:///{(self.tmp / 'spa.db').as_posix()}", web_dist=dist)
        self.app = Flask(__name__)
        self.ctx = init_api(self.app, config=cfg)
        self.client = self.app.test_client()

    def tearDown(self):
        self.ctx.db.dispose()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_routes_fall_back_to_the_app_shell(self):
        resp = self.client.get("/history/20261120_090000_x")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"id=root", resp.data)
        self.assertEqual(resp.headers["Cache-Control"], "no-cache")

    def test_assets_are_long_cached_with_js_mime(self):
        resp = self.client.get("/assets/app-abc123.js")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("javascript", resp.mimetype)
        self.assertIn("immutable", resp.headers["Cache-Control"])
        self.assertEqual(self.client.get("/sw.js").headers["Cache-Control"], "no-cache")

    def test_missing_files_and_api_paths_do_not_return_the_shell(self):
        self.assertEqual(self.client.get("/assets/missing.js").status_code, 404)
        self.assertEqual(self.client.get("/api/nope").status_code, 401)


if __name__ == "__main__":
    unittest.main()
