from datetime import datetime, timezone

from app import auth
from fastapi import HTTPException
import pytest


def test_code_format_and_randomness():
    codes = {auth.generate_access_code() for _ in range(200)}
    assert len(codes) == 200
    assert all(c.startswith("NTRI-") and len(c) == 14 for c in codes)


def test_digest_is_not_plaintext(monkeypatch):
    monkeypatch.setattr(auth, "SECRET", "x" * 32)
    raw = "NTRI-ABCD-2345"
    assert auth._digest(raw, "code") != raw
    assert auth._digest(raw, "code") == auth._digest(raw, "code")


def test_client_cannot_pass_admin_guard():
    with pytest.raises(HTTPException) as exc:
        auth.require_admin({"role": "client"})
    assert exc.value.status_code == 403
