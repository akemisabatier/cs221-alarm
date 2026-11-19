# Adaptive Alarm

CS221 (Autumn 2026) project, Impact track. A phone app that learns from your nights and recommends when to go to bed so you wake up rested.

## What it does

- **Plan tonight:** set a wake-up time and get a recommended bedtime and amount of sleep.
- **Going to bed / I'm awake:** one tap at night and one in the morning record when you slept and woke.
- **Morning check-in:** log how many times you snoozed and rate how rested you feel from 1 to 10.
- **Sleep log:** view, edit, add or delete nights.
- **Insights:** your "sweet spot" amount of sleep, plus average rested score by time asleep and by number of snoozes.
- **Team export:** a CSV of every participant's completed nights (labeled P1, P2, …) for training the model.

The recommendation is currently a simple baseline: the average time asleep on your best-rated nights, once you have logged at least 5. The team's model will replace it.

## Data collected per night

| Field | Example |
|---|---|
| Bedtime | 11:15 PM |
| Wake time | 8:00 AM |
| Number of snoozes | 1 |
| Rested score (1–10) | 7 |

## How it runs

The app is a single file, `app/index.html` (HTML, CSS and vanilla JavaScript, with no build step). It is hosted as a Claude artifact, and saves data through that platform's shared database (`claude.use("db")`), so users must be signed in to Claude.

To use it on an iPhone, open the app link in Safari, then tap Share › Add to Home Screen.

**Limitation:** a web app cannot ring while the phone is locked, so users set their iPhone Clock alarm to the app's wake-up time. A native alarm (iOS AlarmKit) or a Shortcuts integration is planned.

Opening `app/index.html` directly in a browser shows the interface, but nothing is saved outside the hosted version.

## Repository layout

```
app/index.html    the phone web app
docs/             screenshots of the UI design (add as you go)
```

## Team

- Akemi: UI and frontend
- Lawrence, Angela: backend, data and model
