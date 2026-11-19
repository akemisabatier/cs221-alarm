"""Run from the project folder: python -m uvicorn app:app --reload"""

import csv
import hmac
import io
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import ValidationError

import database
import recommender
from schemas import FinishBedtimeIn, NightIn, StartBedtimeIn


@asynccontextmanager
async def lifespan(_app: FastAPI):
    database.initialize()
    yield


app = FastAPI(
    title="Snooze Signals API",
    description="Local CS221 prototype: sleep logs, insights, bedtime recommendations, CSV exports",
    version="0.1.0",
    lifespan=lifespan,
)

# Update this list to include your own local frontend's origin if necessary.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000",
                   "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)


def csv_response(rows, filename):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    columns = ["participant_id", "bedtime", "wake_time", "sleep_hours", "snoozes", "restedness"]
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row[key] for key in columns])
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/health")
def health():
    return {"status": "ok", "project": "Snooze Signals"}


@app.post("/nights", status_code=201)
def create_night(night: NightIn):
    """Log a completed night directly (used by Sleep Log → Add night)."""
    identifier = database.insert_night(night)
    return {"id": identifier, "message": "Night logged"}


@app.post("/bedtime/start")
def start_bedtime(body: StartBedtimeIn):
    """Called when the user presses 'Going to bed'."""
    database.start_bedtime(body.participant_id, body.bedtime)
    return {"message": "Bedtime recorded. Complete this night after waking up."}


@app.post("/bedtime/finish", status_code=201)
def finish_bedtime(body: FinishBedtimeIn):
    """Complete the pending night when the user wakes up."""
    try:
        identifier = database.finish_bedtime(
            body.participant_id, body.wake_time, body.snoozes, body.restedness
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if identifier is None:
        raise HTTPException(status_code=404, detail="No pending bedtime for this participant")
    return {"id": identifier, "message": "Night completed"}


@app.get("/nights/{participant_id}")
def read_nights(participant_id: str = Path(pattern=r"^[A-Za-z0-9_-]{1,60}$")):
    return {"participant_id": participant_id, "nights": database.nights_for(participant_id)}


@app.get("/insights/{participant_id}")
def read_insights(participant_id: str = Path(pattern=r"^[A-Za-z0-9_-]{1,60}$")):
    return recommender.insights(database.nights_for(participant_id))


@app.get("/recommendation/{participant_id}")
def read_recommendation(
    participant_id: str = Path(pattern=r"^[A-Za-z0-9_-]{1,60}$"),
    wake_time: str = Query(default="08:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$"),
):
    return recommender.recommend(database.nights_for(participant_id), wake_time)


@app.get("/export/{participant_id}.csv")
def export_own_nights(participant_id: str = Path(pattern=r"^[A-Za-z0-9_-]{1,60}$")):
    # For this local class prototype, participant IDs are not authentication.
    return csv_response(database.nights_for(participant_id), f"{participant_id}_sleep_log.csv")


@app.get("/team/export.csv")
def export_team(x_admin_token: str | None = Header(default=None)):
    """Protected team CSV. Set SNOOZE_ADMIN_TOKEN before starting the server."""
    secret = os.environ.get("SNOOZE_ADMIN_TOKEN")
    if not secret or not x_admin_token or not hmac.compare_digest(x_admin_token, secret):
        raise HTTPException(status_code=403, detail="Team CSV export requires valid X-Admin-Token")
    return csv_response(database.all_nights(), "team_sleep_data.csv")
