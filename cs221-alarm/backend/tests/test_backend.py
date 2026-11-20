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


# ---- Web app sync endpoints (PUT/DELETE by app-generated id) -------------------------

def app_night(hours=8.0, rating=7, snoozes=1, day=0):
    wake_ms = int(datetime(2026, 11, 10, 15, 0).timestamp() * 1000) + day * 86_400_000
    return {"bedAt": wake_ms - int(hours * 3_600_000), "wakeAt": wake_ms,
            "snoozes": snoozes, "rating": rating, "tzOffset": 480}


def test_upsert_is_idempotent_and_updates(client):
    url = "/nights/P1/3f2b9c1e-aaaa-bbbb-cccc-1234567890ab"
    first = client.put(url, json=app_night())
    assert first.status_code == 200 and first.json()["created"] is True
    retry = client.put(url, json=app_night())            # the offline queue may resend
    assert retry.json()["created"] is False
    client.put(url, json=app_night(rating=3, snoozes=2))  # editing a night
    nights = client.get("/nights/P1").json()["nights"]
    assert len(nights) == 1
    row = nights[0]
    assert row["client_id"] == "3f2b9c1e-aaaa-bbbb-cccc-1234567890ab"
    assert row["restedness"] == 3 and row["snoozes"] == 2
    assert row["sleep_hours"] == 8.0
    assert row["bed_ms"] < row["wake_ms"]


def test_delete_is_idempotent_and_scoped_to_participant(client):
    client.put("/nights/P1/night-aaaaaa", json=app_night())
    client.put("/nights/P2/night-aaaaaa", json=app_night())   # same id, other person
    assert client.delete("/nights/P1/night-aaaaaa").json()["deleted"] == 1
    assert client.delete("/nights/P1/night-aaaaaa").json()["deleted"] == 0
    assert client.get("/nights/P1").json()["nights"] == []
    assert len(client.get("/nights/P2").json()["nights"]) == 1


def test_upsert_validation(client):
    url = "/nights/P1/night-bbbbbb"
    assert client.put(url, json={**app_night(), "rating": 11}).status_code == 422
    assert client.put(url, json={**app_night(), "snoozes": 31}).status_code == 422
    bad = app_night()
    bad["wakeAt"] = bad["bedAt"] - 1
    assert client.put(url, json=bad).status_code == 422
    assert client.put("/nights/P1/bad%20id", json=app_night()).status_code == 422


def test_app_nights_feed_recommendation_and_cors(client):
    for day in range(5):
        client.put(f"/nights/P1/night-{day:06d}", json=app_night(7 + day * 0.5, 5 + day, day=day))
    rec = client.get("/recommendation/P1?wake_time=07:30").json()
    assert rec["method"] == "experimental_mdp" and rec["nights_logged"] == 5
    preflight = client.options("/nights/P1/night-000000", headers={
        "Origin": "http://localhost:8000", "Access-Control-Request-Method": "DELETE"})
    assert preflight.status_code == 200


def test_frontend_is_served_from_same_origin(client):
    page = client.get("/")
    assert page.status_code == 200 and "Adaptive Alarm" in page.text
    assert client.get("/manifest.json").status_code == 200
