# Adaptive Alarm

CS221 (Autumn 2026) project, Impact track. A phone web app that learns from your nights and recommends when to go to bed so you wake up rested.

## What it does

- **Plan tonight:** set a wake-up time and get a recommended bedtime and amount of sleep.
- **Going to bed / I'm awake:** one tap at night and one in the morning record when you slept and woke.
- **Morning check-in:** log how many times you snoozed and rate how rested you feel from 1 to 10.
- **Sleep log:** view, edit, add or delete nights.
- **Insights:** your "sweet spot" amount of sleep, plus average rested score by time asleep and by number of snoozes.
- **Participant codes:** users join with a code (P1, P2, …), not a name or account.

The recommendation is currently a simple baseline: the average time asleep on your best-rated nights, once you have logged at least 5. The team's model will replace it.

## Data collected per night

Each completed night becomes one row in the team's Google Sheet (tab `nights`):

| Column | Example |
|---|---|
| participant | P1 |
| bed_time / wake_time | 2026-11-19 23:15 / 2026-11-20 08:00 |
| hours_asleep | 8.75 |
| snoozes | 1 |
| rating (1–10) | 7 |
| bed_ms / wake_ms, tz_offset_min, saved_at | raw timestamps for analysis |

To train the model, use File › Download › CSV in the Sheet.

## Architecture

- `index.html`: the whole app (HTML, CSS, vanilla JavaScript, no build step), hosted on Vercel.
- `apps-script/Code.gs`: a Google Apps Script web app that reads and writes the Google Sheet.
- On the phone, the participant code, wake-up time and tonight's in-progress night are kept in the browser's local storage. Changes made offline are queued and uploaded when the phone is back online.

## Setup

### 1. Google Sheet backend (about 5 minutes, once)

1. Create a new Google Sheet, for example "CS221 Adaptive Alarm data".
2. Go to **Extensions › Apps Script**. Delete the sample code, paste in all of `apps-script/Code.gs`, and save.
3. Click **Deploy › New deployment**. Choose the gear icon › **Web app**, then set:
   - Execute as: **Me**
   - Who has access: **Anyone**
4. Click **Deploy**, approve the permissions (choose your account, then Advanced › Go to project), and copy the **Web app URL**. It ends in `/exec`.
5. In `index.html`, replace `PASTE_YOUR_APPS_SCRIPT_URL_HERE` with that URL. Then commit.

If you later change `Code.gs`, use **Deploy › Manage deployments › Edit › New version**, so the URL stays the same.

### 2. Hosting on Vercel (about 5 minutes, once)

1. Sign up at vercel.com with GitHub. The free Hobby plan is enough.
2. **Add New › Project**, then import this repository.
3. Leave all settings as they are (Framework preset: Other, no build command), and click **Deploy**.

Every push to `main` redeploys the app automatically.

### 3. On a phone

Open the Vercel link in Safari, then tap Share › **Add to Home Screen**. Open it from the home screen icon and enter your participant code.

The home screen app and Safari keep separate storage on iPhone, so enter your code in whichever one you use.

## Limitations

- **No ringing:** a web app cannot ring while the phone is locked, so users set their iPhone Clock alarm to the app's wake-up time. A native alarm (iOS AlarmKit) or a Shortcuts integration is planned.
- **Open endpoint:** the Apps Script endpoint has no login. Anyone with its URL could add rows under any participant code. That is acceptable for a small class study, and is discussed in the report's ethical considerations.

## Team

- Akemi: UI and frontend
- Lawrence, Angela: backend, data and model
