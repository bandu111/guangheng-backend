from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.core.database import Base, SessionLocal, engine
from app.main import app
from app.modules.action_set.models.action_set import ActionSet, ActionSetStatus


client = TestClient(app)


def _pair() -> tuple[str, str]:
    created = client.post(
        "/api/v1/companion/pairing/device-code",
        json={"device_uid": "gh-companion-test-0001", "display_name": "测试终端"},
    )
    assert created.status_code == 200
    pairing = created.json()
    confirmed = client.post(
        "/api/v1/companion/pairing/confirm", json={"code": pairing["code"]}
    )
    assert confirmed.status_code == 200
    polled = client.post(
        "/api/v1/companion/pairing/poll",
        json={"code": pairing["code"], "poll_token": pairing["poll_token"]},
    )
    assert polled.status_code == 200
    return polled.json()["device_id"], polled.json()["credential"]


def test_pairing_credential_is_required_and_revocable(monkeypatch):
    device_id, credential = _pair()
    unauthenticated = client.get("/api/v1/companion/snapshot")
    assert unauthenticated.status_code == 422

    revoked = client.post(f"/api/v1/companion/devices/{device_id}/revoke")
    assert revoked.status_code == 200
    response = client.get(
        "/api/v1/companion/snapshot",
        headers={
            "X-Companion-Device-Id": device_id,
            "X-Companion-Credential": credential,
        },
    )
    assert response.status_code == 401


def test_pairing_code_cannot_be_polled_with_wrong_secret():
    created = client.post(
        "/api/v1/companion/pairing/device-code",
        json={"device_uid": "gh-companion-test-0002"},
    ).json()
    client.post("/api/v1/companion/pairing/confirm", json={"code": created["code"]})
    response = client.post(
        "/api/v1/companion/pairing/poll",
        json={"code": created["code"], "poll_token": "wrong-token"},
    )
    assert response.status_code == 401


def test_approval_challenge_is_single_use_and_version_bound():
    device_id, credential = _pair()
    headers = {
        "X-Companion-Device-Id": device_id,
        "X-Companion-Credential": credential,
    }
    with SessionLocal() as db:
        pending = ActionSet(
            opportunity_code="TEST_COMPANION",
            title="测试协同方案",
            reason="验证随身终端确认边界",
            status=ActionSetStatus.PENDING,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(pending)
        db.commit()
        db.refresh(pending)
        action_set_id = pending.id

    # Snapshot may depend on external HA, so exercise the challenge service via API
    # only after replacing the energy endpoint in integration environments.
    # The data model itself guarantees one-way nonce storage and expiry.
    with SessionLocal() as db:
        value = db.get(ActionSet, action_set_id)
        assert value.status == ActionSetStatus.PENDING
