from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app


def test_autonomy_level_is_persisted_and_full_access_remains_safety_guarded():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            initial = client.get("/api/v1/autonomy/level")
            shadow = client.put(
                "/api/v1/autonomy/level", json={"level": "SHADOW"}
            )
            persisted = client.get("/api/v1/autonomy/level")
            status = client.get("/api/v1/autonomy/status")
            auto = client.put(
                "/api/v1/autonomy/level", json={"level": "AUTO"}
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()

    assert initial.status_code == 200
    assert initial.json()["level"] == "CONFIRM"
    assert len(initial.json()["options"]) == 4
    assert shadow.status_code == 200
    assert shadow.json()["permissions"] == {
        "observe": True,
        "optimize": True,
        "propose": False,
        "execute_without_approval": False,
    }
    assert persisted.json()["level"] == "SHADOW"
    assert status.json()["autonomy_level"] == "SHADOW"
    assert auto.status_code == 200
    assert auto.json()["level"] == "AUTO"
    assert auto.json()["permissions"]["execute_without_approval"] is False
