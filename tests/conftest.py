"""
Shared test setup.

Every API route now sits behind a session. The suites that existed before
that are about their own endpoints, not about the gate, so they are given a
signed-in caller rather than being rewritten to log in — one place to change
if the gate ever changes again.

`tests/test_auth.py` opts out: it is the suite that exercises the real thing,
and a bypass would make it pass no matter what.
"""
import uuid

import pytest

from src.models import User


@pytest.fixture(autouse=True)
def signed_in_by_default(request, monkeypatch):
    """
    Answers the middleware's session lookup with an admin.

    Patching the lookup rather than disabling the middleware keeps the real
    code path in play: routes are still resolved through it, so a route that
    forgets its dependencies still fails here the way it would in production.
    """
    if request.node.fspath.basename == "test_auth.py":
        yield
        return

    admin = User(
        user_id=uuid.uuid4().hex,
        email="test-admin@eko.co.in",
        full_name="Test Admin",
        password_hash="!",
        role="admin",
        status="APPROVED",
    )

    import src.services.auth_service as auth_service
    monkeypatch.setattr(auth_service, "user_from_token", lambda db, token: admin)

    # No cookie is set: several suites build their TestClient at import time,
    # before any fixture runs, so anything done to the client here would come
    # too late. The lookup is consulted for every request regardless, which is
    # what makes patching it sufficient.
    yield
