from datetime import datetime, timedelta
import os
import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SNOOZE_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SNOOZE_ADMIN_TOKEN", "test-secret")
    with TestClient(app) as instance:
        yield instance


def night_data(index=0, score=7):
    wake = datetime(2026, 11, 10, 8, 0) + timedelta(days=index)
    hours = [7.0, 8.0, 7.5, 8.5, 9.0][index % 5]
    return {
        "participant_id": "P1", "bedtime": (wake - timedelta(hours=hours)).isoformat(),
        "wake_time": wake.isoformat(), "snoozes": 1, "restedness": score,
    }


def test_log_insights_and_recommendation(client):
    assert client.get("/health").json()["status"] == "ok"
    initial = client.get("/recommendation/P1?wake_time=08:00").json()
    assert initial["suggested_bedtime"] == "00:00"
    assert initial["method"] == "default_8h"

    for index in range(5):
        response = client.post("/nights", json=night_data(index, 6 + index % 4))
        assert response.status_code == 201, response.text

    assert len(client.get("/nights/P1").json()["nights"]) == 5
    assert client.get("/insights/P1").json()["nights_logged"] == 5
    personalized = client.get("/recommendation/P1?wake_time=08:00").json()
    assert personalized["method"] == "experimental_mdp"
    assert personalized["target_sleep_hours"] in (7, 7.5, 8, 8.5, 9, 9.5)
    assert client.get("/export/P1.csv").text.count("\n") == 6


def test_pending_bedtime_workflow(client):
    start = client.post("/bedtime/start", json={
        "participant_id": "P2", "bedtime": "2026-11-15T23:30:00"})
    assert start.status_code == 200
    finish = client.post("/bedtime/finish", json={
        "participant_id": "P2", "wake_time": "2026-11-16T08:00:00",
        "snoozes": 0, "restedness": 9})
    assert finish.status_code == 201, finish.text
    assert len(client.get("/nights/P2").json()["nights"]) == 1
    assert client.post("/bedtime/finish", json={
        "participant_id": "P2", "wake_time": "2026-11-16T08:00:00",
        "snoozes": 0, "restedness": 9}).status_code == 404


def test_input_validation_and_team_access(client):
    invalid = night_data()
    invalid["restedness"] = 11
    assert client.post("/nights", json=invalid).status_code == 422
    assert client.get("/team/export.csv").status_code == 403
    assert client.get("/team/export.csv", headers={"X-Admin-Token": "test-secret"}).status_code == 200
    assert client.get("/recommendation/P1?wake_time=25:00").status_code == 422
