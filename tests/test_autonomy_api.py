from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.modules.autonomy.models.autonomous_decision_run import (
    AutonomousDecisionRun,
    AutonomousRunStatus,
    AutonomousTriggerType,
)
from app.modules.autonomy.models.notification_event import (
    NotificationEvent,
    NotificationEventType,
    NotificationSeverity,
    NotificationStatus,
)


def test_status_decision_and_notification_http_contracts():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    now = datetime.utcnow()
    run = AutonomousDecisionRun(
        trigger_type=AutonomousTriggerType.MANUAL,
        status=AutonomousRunStatus.COMPLETED,
        started_at=now,
        completed_at=now,
        strategy="BACKUP",
        capability="backup_reserve",
        current_value=80,
        target_value=80,
        action_required=False,
        reason_code="TARGET_ALREADY_SATISFIED",
        confidence="LOW",
        result_code="NO_ACTION_REQUIRED",
        decision_version="v2",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    event = NotificationEvent(
        event_type=NotificationEventType.SYSTEM_WARNING,
        title="测试告警",
        message="结构化测试告警",
        severity=NotificationSeverity.WARNING,
        status=NotificationStatus.UNREAD,
        decision_run_id=run.id,
        dedupe_key="test:warning",
        payload={"error_code": "TEST_WARNING"},
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            status = client.get("/api/v1/autonomy/status")
            decisions = client.get("/api/v1/autonomy/decisions?limit=10")
            detail = client.get(f"/api/v1/autonomy/decisions/{run.id}")
            notifications = client.get("/api/v1/notifications?status=UNREAD")
            read = client.patch(f"/api/v1/notifications/{event.id}/read")
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()

    assert status.status_code == 200
    assert status.json()["agent_state"] == "MONITORING"
    assert status.json()["latest_decision"]["reason_code"] == (
        "TARGET_ALREADY_SATISFIED"
    )
    assert status.json()["pending_proposal"] is None
    assert decisions.json()["count"] == 1
    assert detail.json()["result_code"] == "NO_ACTION_REQUIRED"
    assert notifications.json()["count"] == 1
    assert read.json()["status"] == "READ"
    assert read.json()["read_at"] is not None
