"""
Who can ask for access, and who actually gets it.

The two gates are deliberately separate — the email domain decides who may
request, an admin decides who gets in — so both are pinned down here, along
with the rule that everything else stays closed until then.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base, get_db
from src.main import app
from src.models import User  # noqa: F401  (registers the tables)
from src.services import auth_service as auth

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

GOOD_PASSWORD = "correct-horse-7"


def override_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(monkeypatch):
    # Set per test, not at import: dependency_overrides is global, other
    # suites point it at their own database from module scope, and whichever
    # imported last would otherwise win for the whole run.
    app.dependency_overrides[get_db] = override_db
    # The middleware opens its own session, so it has to be pointed at the
    # test database too or every request would 401 against an empty one.
    monkeypatch.setattr("src.database.SessionLocal", TestingSessionLocal)
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-secret-long-enough-for-hs256")
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    db = TestingSessionLocal()
    db.query(User).delete()
    db.commit()
    db.close()


def make_admin(email="admin@eko.co.in"):
    db = TestingSessionLocal()
    db.add(User(user_id=uuid.uuid4().hex, email=email,
                password_hash=auth.hash_password(GOOD_PASSWORD),
                role="admin", status="APPROVED"))
    db.commit()
    db.close()
    return email


class TestEmailDomain:
    @pytest.mark.parametrize("email", [
        "someone@gmail.com",
        "someone@eko.com",
        "someone@notek.co.in",
        # The domain has to terminate the address, not merely appear in it.
        "someone@eko.co.in.attacker.com",
        "eko.co.in@gmail.com",
        "not-an-email",
    ])
    def test_rejected(self, email):
        assert auth.email_is_allowed(email) is False

    @pytest.mark.parametrize("email", [
        "mansi.kanchan.intern@eko.co.in",
        "A.Person@EKO.CO.IN",
    ])
    def test_allowed(self, email):
        assert auth.email_is_allowed(email) is True


class TestSignup:
    def test_outside_domain_is_refused(self, client):
        r = client.post("/api/v1/auth/signup",
                        json={"email": "outsider@gmail.com", "password": GOOD_PASSWORD})
        assert r.status_code == 400
        assert "eko.co.in" in r.json()["detail"]

    def test_signup_does_not_grant_access(self, client):
        r = client.post("/api/v1/auth/signup",
                        json={"email": "new@eko.co.in", "password": GOOD_PASSWORD})
        assert r.status_code == 201
        assert r.json()["status"] == "PENDING"

        # The whole point: a recorded request is not an account that works.
        login = client.post("/api/v1/auth/login",
                            json={"email": "new@eko.co.in", "password": GOOD_PASSWORD})
        assert login.status_code == 403
        assert "approval" in login.json()["detail"].lower()

    def test_weak_password_is_refused(self, client):
        r = client.post("/api/v1/auth/signup",
                        json={"email": "weak@eko.co.in", "password": "1234567890"})
        assert r.status_code == 400

    def test_duplicate_request_is_refused(self, client):
        client.post("/api/v1/auth/signup",
                    json={"email": "dupe@eko.co.in", "password": GOOD_PASSWORD})
        again = client.post("/api/v1/auth/signup",
                            json={"email": "dupe@eko.co.in", "password": GOOD_PASSWORD})
        assert again.status_code == 409


class TestLogin:
    def test_unknown_and_wrong_password_are_indistinguishable(self, client):
        make_admin("real@eko.co.in")
        missing = client.post("/api/v1/auth/login",
                              json={"email": "ghost@eko.co.in", "password": GOOD_PASSWORD})
        wrong = client.post("/api/v1/auth/login",
                            json={"email": "real@eko.co.in", "password": "wrong-password-9"})
        # Otherwise the form tells an attacker which addresses exist.
        assert missing.status_code == wrong.status_code == 401
        assert missing.json()["detail"] == wrong.json()["detail"]

    def test_approved_user_can_sign_in(self, client):
        email = make_admin()
        r = client.post("/api/v1/auth/login",
                        json={"email": email, "password": GOOD_PASSWORD})
        assert r.status_code == 200
        assert r.json()["role"] == "admin"
        assert auth.COOKIE_NAME in r.cookies


class TestApprovalFlow:
    def test_admin_approves_and_the_user_can_then_sign_in(self, client):
        client.post("/api/v1/auth/signup",
                    json={"email": "wants-in@eko.co.in", "password": GOOD_PASSWORD})
        admin = make_admin()
        client.post("/api/v1/auth/login", json={"email": admin, "password": GOOD_PASSWORD})

        pending = client.get("/api/v1/auth/users?status=PENDING").json()
        assert [u["email"] for u in pending] == ["wants-in@eko.co.in"]

        approved = client.post(f"/api/v1/auth/users/{pending[0]['user_id']}/approve")
        assert approved.status_code == 200
        assert approved.json()["status"] == "APPROVED"
        assert approved.json()["decided_by"] == admin

        client.post("/api/v1/auth/logout")
        r = client.post("/api/v1/auth/login",
                        json={"email": "wants-in@eko.co.in", "password": GOOD_PASSWORD})
        assert r.status_code == 200

    def test_members_cannot_reach_the_queue(self, client):
        client.post("/api/v1/auth/signup",
                    json={"email": "member@eko.co.in", "password": GOOD_PASSWORD})
        admin = make_admin()
        client.post("/api/v1/auth/login", json={"email": admin, "password": GOOD_PASSWORD})
        uid = client.get("/api/v1/auth/users?status=PENDING").json()[0]["user_id"]
        client.post(f"/api/v1/auth/users/{uid}/approve")
        client.post("/api/v1/auth/logout")

        client.post("/api/v1/auth/login",
                    json={"email": "member@eko.co.in", "password": GOOD_PASSWORD})
        assert client.get("/api/v1/auth/users").status_code == 403
        assert client.post(f"/api/v1/auth/users/{uid}/reject", json={}).status_code == 403

    def test_rejected_user_cannot_sign_in(self, client):
        client.post("/api/v1/auth/signup",
                    json={"email": "nope@eko.co.in", "password": GOOD_PASSWORD})
        admin = make_admin()
        client.post("/api/v1/auth/login", json={"email": admin, "password": GOOD_PASSWORD})
        uid = client.get("/api/v1/auth/users?status=PENDING").json()[0]["user_id"]
        client.post(f"/api/v1/auth/users/{uid}/reject", json={"reason": "not on this project"})
        client.post("/api/v1/auth/logout")

        r = client.post("/api/v1/auth/login",
                        json={"email": "nope@eko.co.in", "password": GOOD_PASSWORD})
        assert r.status_code == 403


class TestEverythingElseIsClosed:
    @pytest.mark.parametrize("path", [
        "/api/v1/stats",
        "/api/v1/businesses",
        "/api/v1/whatsapp/campaigns",
        "/api/v1/config/locations",
        "/openapi.json",
    ])
    def test_api_requires_a_session(self, client, path):
        assert client.get(path).status_code == 401

    @pytest.mark.parametrize("path", ["/health", "/ready"])
    def test_probes_stay_open(self, client, path):
        # Docker's healthcheck and any monitoring carry no cookie.
        assert client.get(path).status_code in (200, 503)

    def test_the_meta_webhook_stays_open(self, client):
        # Meta cannot present a session cookie; that endpoint is guarded by
        # its own signature check instead.
        r = client.get("/api/v1/whatsapp/webhook",
                       params={"hub.mode": "subscribe", "hub.challenge": "1",
                               "hub.verify_token": "wrong"})
        assert r.status_code == 403  # reached the handler, not the gate

    def test_signing_in_opens_the_rest(self, client):
        email = make_admin()
        client.post("/api/v1/auth/login", json={"email": email, "password": GOOD_PASSWORD})
        assert client.get("/api/v1/stats").status_code == 200


class TestBootstrapAdmin:
    """
    The seeded admin exists before anyone signs up. Signup proves only that
    an address is on the domain, not that the person typing it owns the
    mailbox, so it must never be the way that account gets its password.
    """

    def test_signup_cannot_claim_the_seeded_admin(self, client):
        res = client.post("/api/v1/auth/signup", json={
            "email": auth.BOOTSTRAP_ADMIN, "password": GOOD_PASSWORD,
        })
        assert res.status_code == 409

        res = client.post("/api/v1/auth/login", json={
            "email": auth.BOOTSTRAP_ADMIN, "password": GOOD_PASSWORD,
        })
        assert res.status_code == 401

    def test_password_comes_from_configuration(self, monkeypatch):
        monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", GOOD_PASSWORD)
        db = TestingSessionLocal()
        try:
            auth.ensure_bootstrap_admin(db)
            user = db.query(User).filter(User.email == auth.BOOTSTRAP_ADMIN).one()
            assert user.role == "admin" and user.status == "APPROVED"
            assert auth.verify_password(GOOD_PASSWORD, user.password_hash)
        finally:
            db.query(User).delete()
            db.commit()
            db.close()

    def test_configured_password_never_overwrites_one_already_set(self, monkeypatch):
        db = TestingSessionLocal()
        try:
            db.add(User(user_id=uuid.uuid4().hex, email=auth.BOOTSTRAP_ADMIN,
                        password_hash=auth.hash_password("existing-pass-1"),
                        role="admin", status="APPROVED"))
            db.commit()
            monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", GOOD_PASSWORD)
            auth.ensure_bootstrap_admin(db)
            user = db.query(User).filter(User.email == auth.BOOTSTRAP_ADMIN).one()
            assert auth.verify_password("existing-pass-1", user.password_hash)
        finally:
            db.query(User).delete()
            db.commit()
            db.close()

    def test_weak_configured_password_is_ignored(self, monkeypatch):
        monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "short")
        db = TestingSessionLocal()
        try:
            auth.ensure_bootstrap_admin(db)
            user = db.query(User).filter(User.email == auth.BOOTSTRAP_ADMIN).one()
            assert not auth.has_usable_password(user)
        finally:
            db.query(User).delete()
            db.commit()
            db.close()


class TestManagerRole:
    """
    A manager sees everything a member does and carries the tag. The
    approvals queue stays with the administrator: nothing grants it.
    """

    def _pending(self, client, email="kavya.shukla@eko.co.in"):
        client.post("/api/v1/auth/signup", json={"email": email, "password": GOOD_PASSWORD})
        client.post("/api/v1/auth/login", json={"email": make_admin(), "password": GOOD_PASSWORD})
        return client.get("/api/v1/auth/users?status=PENDING").json()[0]["user_id"]

    def test_a_request_can_be_approved_as_manager(self, client):
        uid = self._pending(client)
        res = client.post(f"/api/v1/auth/users/{uid}/approve", json={"role": "manager"})
        assert res.status_code == 200 and res.json()["role"] == "manager"
        assert res.json()["status"] == "APPROVED"

    def test_a_manager_sees_the_app_but_not_the_approvals_queue(self, client):
        uid = self._pending(client)
        client.post(f"/api/v1/auth/users/{uid}/approve", json={"role": "manager"})
        client.post("/api/v1/auth/logout")

        me = client.post("/api/v1/auth/login",
                         json={"email": "kavya.shukla@eko.co.in", "password": GOOD_PASSWORD})
        assert me.status_code == 200 and me.json()["role"] == "manager"
        assert client.get("/api/v1/stats").status_code == 200
        assert client.get("/api/v1/whatsapp/templates").status_code == 200
        assert client.get("/api/v1/auth/users").status_code == 403
        assert client.post(f"/api/v1/auth/users/{uid}/approve", json={"role": "manager"}).status_code == 403

    def test_admin_cannot_be_granted(self, client):
        uid = self._pending(client)
        res = client.post(f"/api/v1/auth/users/{uid}/approve", json={"role": "admin"})
        assert res.status_code == 400
        db = TestingSessionLocal()
        assert db.query(User).filter(User.user_id == uid).one().status == "PENDING"
        db.close()

    def test_approving_without_a_role_gives_the_least_access(self, client):
        """Member is view-only, so a role nobody chose is the safe one."""
        uid = self._pending(client)
        res = client.post(f"/api/v1/auth/users/{uid}/approve")
        assert res.json()["role"] == "member"

    def test_a_role_can_be_changed_later_but_not_the_administrators(self, client):
        uid = self._pending(client)
        client.post(f"/api/v1/auth/users/{uid}/approve")
        assert client.post(f"/api/v1/auth/users/{uid}/approve", json={"role": "manager"}).json()["role"] == "manager"
        admin_id = next(u["user_id"] for u in client.get("/api/v1/auth/users").json() if u["role"] == "admin")
        assert client.post(f"/api/v1/auth/users/{admin_id}/approve", json={"role": "member"}).status_code == 400


class TestViewOnlyMember:
    """A member may look at everything on their tabs and change nothing."""

    @pytest.fixture
    def member(self, client):
        client.post("/api/v1/auth/signup", json={"email": "viewer@eko.co.in", "password": GOOD_PASSWORD})
        client.post("/api/v1/auth/login", json={"email": make_admin(), "password": GOOD_PASSWORD})
        uid = client.get("/api/v1/auth/users?status=PENDING").json()[0]["user_id"]
        assert client.post(f"/api/v1/auth/users/{uid}/approve", json={"role": "member"}).json()["role"] == "member"
        client.post("/api/v1/auth/logout")
        assert client.post("/api/v1/auth/login",
                           json={"email": "viewer@eko.co.in", "password": GOOD_PASSWORD}).json()["role"] == "member"
        return client

    @pytest.mark.parametrize("path", [
        "/api/v1/stats", "/api/v1/businesses", "/api/v1/whatsapp/templates",
        "/api/v1/whatsapp/campaigns", "/api/v1/whatsapp/insights/playbook",
        "/api/v1/discovery/autopilot",
    ])
    def test_can_read(self, member, path):
        assert member.get(path).status_code == 200

    @pytest.mark.parametrize("method, path, body", [
        ("put", "/api/v1/discovery/autopilot", {"enabled": True}),
        ("post", "/api/v1/discovery/batch", {}),
        ("post", "/api/v1/discovery/stop", None),
        ("post", "/api/v1/whatsapp/templates", {"name": "x", "body": "y"}),
        ("delete", "/api/v1/whatsapp/templates/abc", None),
        ("post", "/api/v1/whatsapp/campaigns", {}),
        ("post", "/api/v1/whatsapp/campaigns/abc/cancel", None),
        ("post", "/api/v1/whatsapp/leads/abc/reply", {"body": "hi"}),
        ("post", "/api/v1/jobs/retry-all", None),
        ("post", "/api/v1/config/sync", None),
        ("post", "/api/v1/export/google-sheets/sync", None),
        ("post", "/api/v1/whatsapp/studio/from-messages", {}),
    ])
    def test_cannot_change_anything(self, member, method, path, body):
        res = getattr(member, method)(path, json=body) if body is not None else getattr(member, method)(path)
        assert res.status_code == 403, f"{method.upper()} {path} -> {res.status_code}"
        assert "view-only" in res.json()["detail"]

    def test_can_still_sign_out_and_count_an_audience(self, member):
        assert member.post("/api/v1/whatsapp/audience/summary", json={}).status_code == 200
        assert member.post("/api/v1/auth/logout").status_code == 200

    def test_cannot_see_the_approvals_queue(self, member):
        assert member.get("/api/v1/auth/users").status_code == 403

    @pytest.mark.parametrize("role", ["operator", "manager"])
    def test_operators_and_managers_can_act(self, client, role):
        client.post("/api/v1/auth/signup", json={"email": "doer@eko.co.in", "password": GOOD_PASSWORD})
        client.post("/api/v1/auth/login", json={"email": make_admin(), "password": GOOD_PASSWORD})
        uid = client.get("/api/v1/auth/users?status=PENDING").json()[0]["user_id"]
        client.post(f"/api/v1/auth/users/{uid}/approve", json={"role": role})
        client.post("/api/v1/auth/logout")
        assert client.post("/api/v1/auth/login", json={
            "email": "doer@eko.co.in", "password": GOOD_PASSWORD}).json()["role"] == role
        assert client.post("/api/v1/discovery/stop").status_code == 200
        assert client.get("/api/v1/auth/users").status_code == 403


class TestAskingForARoleAndLosingAccess:
    def _admin(self, client):
        """Signs in as the administrator, creating the account the first time."""
        db = TestingSessionLocal()
        exists = db.query(User).filter(User.email == "admin@eko.co.in").first() is not None
        db.close()
        email = "admin@eko.co.in" if exists else make_admin()
        client.post("/api/v1/auth/login", json={"email": email, "password": GOOD_PASSWORD})

    def test_a_role_can_be_asked_for_and_is_what_approval_gives(self, client):
        res = client.post("/api/v1/auth/signup", json={
            "email": "asks@eko.co.in", "password": GOOD_PASSWORD, "role": "operator"})
        assert res.status_code == 201
        # Asking is not having: the account still cannot sign in.
        assert client.post("/api/v1/auth/login", json={
            "email": "asks@eko.co.in", "password": GOOD_PASSWORD}).status_code == 403

        self._admin(client)
        pending = client.get("/api/v1/auth/users?status=PENDING").json()[0]
        assert pending["role"] == "operator", "the administrator sees what was asked for"
        approved = client.post(f"/api/v1/auth/users/{pending['user_id']}/approve")
        assert approved.json()["role"] == "operator"

    def test_the_administrator_can_give_a_different_role(self, client):
        client.post("/api/v1/auth/signup", json={
            "email": "asks@eko.co.in", "password": GOOD_PASSWORD, "role": "manager"})
        self._admin(client)
        uid = client.get("/api/v1/auth/users?status=PENDING").json()[0]["user_id"]
        assert client.post(f"/api/v1/auth/users/{uid}/approve", json={"role": "operator"}).json()["role"] == "operator"

    @pytest.mark.parametrize("role", ["admin", "owner", "ADMIN "])
    def test_admin_cannot_be_asked_for(self, client, role):
        res = client.post("/api/v1/auth/signup", json={
            "email": "asks@eko.co.in", "password": GOOD_PASSWORD, "role": role})
        assert res.status_code == 400

    def test_removing_access_takes_effect_at_once_and_can_be_undone(self, client):
        client.post("/api/v1/auth/signup", json={"email": "leaver@eko.co.in", "password": GOOD_PASSWORD})
        self._admin(client)
        uid = client.get("/api/v1/auth/users?status=PENDING").json()[0]["user_id"]
        client.post(f"/api/v1/auth/users/{uid}/approve", json={"role": "manager"})
        client.post("/api/v1/auth/logout")

        # Signed in and working...
        assert client.post("/api/v1/auth/login", json={
            "email": "leaver@eko.co.in", "password": GOOD_PASSWORD}).status_code == 200
        assert client.get("/api/v1/stats").status_code == 200
        session = client.cookies.get(auth.COOKIE_NAME)

        # ...until access is removed: the same session stops working.
        client.cookies.clear()
        self._admin(client)
        assert client.post(f"/api/v1/auth/users/{uid}/revoke").json()["status"] == "DISABLED"
        client.cookies.clear()
        client.cookies.set(auth.COOKIE_NAME, session)
        assert client.get("/api/v1/stats").status_code == 401
        client.cookies.clear()
        assert client.post("/api/v1/auth/login", json={
            "email": "leaver@eko.co.in", "password": GOOD_PASSWORD}).status_code == 403

        self._admin(client)
        restored = client.post(f"/api/v1/auth/users/{uid}/approve")
        assert restored.json()["status"] == "APPROVED" and restored.json()["role"] == "manager"

    def test_the_administrators_own_access_cannot_be_removed(self, client):
        self._admin(client)
        me = next(u for u in client.get("/api/v1/auth/users").json() if u["role"] == "admin")
        assert client.post(f"/api/v1/auth/users/{me['user_id']}/revoke").status_code == 400

    def test_only_the_administrator_can_remove_access(self, client):
        client.post("/api/v1/auth/signup", json={"email": "mgr@eko.co.in", "password": GOOD_PASSWORD})
        self._admin(client)
        uid = client.get("/api/v1/auth/users?status=PENDING").json()[0]["user_id"]
        client.post(f"/api/v1/auth/users/{uid}/approve", json={"role": "manager"})
        client.post("/api/v1/auth/logout")
        client.post("/api/v1/auth/login", json={"email": "mgr@eko.co.in", "password": GOOD_PASSWORD})
        assert client.post(f"/api/v1/auth/users/{uid}/revoke").status_code == 403
