# Adaptive Alarm

CS221 (Autumn 2026) project, Impact track. A phone web app that learns from your nights and recommends when to go to bed so you wake up rested.

## What it does

- **Plan tonight:** set a wake-up time and get a recommended bedtime from the team's model.
- **Going to bed / I'm awake:** one tap at night and one in the morning record when you slept and woke.
- **Morning check-in:** log snoozes and rate how rested you feel from 1 to 10.
- **Sleep log:** view, edit, add or delete nights.
- **Insights:** your "sweet spot", plus average rested score by time asleep and by snoozes.
- **Participant codes:** users join with a code (P1, P2, …), not a name or account.

## Architecture

```
index.html, manifest.json, icons   the phone web app (vanilla JS, no build step)
backend/                           FastAPI + SQLite backend
  app.py          routes (and serves the web app from the same origin)
  database.py     SQLite storage and migrations
  recommender.py  value-iteration bedtime model + insights
  schemas.py      request validation
legacy/apps-script/Code.gs         the old Google Sheets backend (no longer used)
```

The app keeps the participant code, wake-up time and the in-progress night in the phone's local storage. Every save or delete is put in an offline queue and sent to the backend, so nothing is lost without signal. Each night has an app-generated id, so a retried save updates the same row instead of duplicating it.

### How the app uses the API

| App action | Request |
|---|---|
| Load nights | `GET /nights/{code}` |
| Save or edit a night | `PUT /nights/{code}/{night_id}` (idempotent) |
| Delete a night | `DELETE /nights/{code}/{night_id}` |
| Tonight's bedtime | `GET /recommendation/{code}?wake_time=HH:MM` (falls back to a local baseline when offline) |
| Team CSV (for the model) | `GET /team/export.csv` with header `X-Admin-Token` |

`/nights` (POST), `/bedtime/start`, `/bedtime/finish`, `/insights/{code}` and `/export/{code}.csv` still exist but the app does not call them.

## Run it

```bash
cd backend
pip install -r requirements.txt
export SNOOZE_ADMIN_TOKEN=pick-a-secret      # protects /team/export.csv
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000 on the same computer. For a phone on the same Wi-Fi, use `http://<your-computer's-ip>:8000`. Then in Safari tap Share › **Add to Home Screen**.

Interactive API docs are at `/docs`. Tests: `cd backend && pip install pytest httpx && python -m pytest`.

Optional demo data: `python seed_demo.py` (synthetic, never study data).

### Environment variables

| Variable | Purpose |
|---|---|
| `SNOOZE_ADMIN_TOKEN` | Required for `/team/export.csv`. |
| `SNOOZE_DB_PATH` | SQLite file location (default `backend/sleep.db`). |
| `SNOOZE_CORS_ORIGINS` | Comma-separated origins, only needed if the app is hosted on a different site than the backend. |

### Hosting the app somewhere else (e.g. Vercel)

Phones need an HTTPS address to reach the backend, and a page served over HTTPS cannot call a plain-HTTP API. To host the page separately: deploy the backend somewhere with HTTPS, set `API_URL` at the top of the script in `index.html` to its address, and set `SNOOZE_CORS_ORIGINS` on the backend to the page's address. SQLite is a file, so use a host with a persistent disk, or the data will be lost on redeploy.

## Limitations

- **No ringing:** a web app cannot ring while the phone is locked, so users set their iPhone Clock alarm to the app's wake-up time.
- **Open endpoints:** participant codes are not authentication; anyone who can reach the server could read or write under any code. Acceptable for a small class study and worth covering in the ethics section of the report.
- The recommendation model is experimental and not medical advice.

## Team

- Akemi: UI and frontend
- Lawrence, Angela: backend, data and model
