"""Optional: generate *synthetic* data for demonstrations. NEVER treat it as study data."""
from datetime import datetime, timedelta

import database
from schemas import NightIn


def main():
    database.initialize()
    for participant_id, offset in (("demo_p1", 0), ("demo_p2", 1)):
        hours_list = [7.0, 8.0, 7.5, 8.5, 8.0, 9.0, 6.5, 8.0, 7.0, 8.5, 9.0, 7.5]
        rested = [5, 7, 6, 8, 7, 9, 3, 7, 5, 8, 9, 6]
        for index, (hours, score) in enumerate(zip(hours_list, rested)):
            wake = datetime(2026, 11, 2, 8, 0) + timedelta(days=index)
            wake += timedelta(minutes=15 * offset)
            bed = wake - timedelta(hours=hours)
            database.insert_night(NightIn(
                participant_id=participant_id, bedtime=bed, wake_time=wake,
                snoozes=2 if score < 6 else (1 if score < 8 else 0),
                restedness=min(10, score + offset),
            ))
    print("Created synthetic nights for demo_p1 and demo_p2.")
    print("Try http://127.0.0.1:8000/recommendation/demo_p1?wake_time=08:00")


if __name__ == "__main__":
    main()
