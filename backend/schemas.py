"""Validation for Snooze Signals JSON requests."""

from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator


class NightIn(BaseModel):
    participant_id: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9_-]+$")
    bedtime: datetime
    wake_time: datetime
    snoozes: int = Field(ge=0, le=30)
    restedness: int = Field(ge=1, le=10)

    @model_validator(mode="after")
    def check_duration(self):
        try:
            hours = (self.wake_time - self.bedtime).total_seconds() / 3600
        except TypeError as exc:
            raise ValueError("Use the same time-zone convention for bedtime and wake_time") from exc
        if not (0 < hours <= 24):
            raise ValueError("Wake time must be after bedtime, within 24 hours")
        return self


class StartBedtimeIn(BaseModel):
    participant_id: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9_-]+$")
    bedtime: datetime


class FinishBedtimeIn(BaseModel):
    participant_id: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9_-]+$")
    wake_time: datetime
    snoozes: int = Field(ge=0, le=30)
    restedness: int = Field(ge=1, le=10)


class BedtimeRecommendationQuery(BaseModel):
    wake_time: str

    @field_validator("wake_time")
    @classmethod
    def validate_clock(cls, value):
        from datetime import time
        try:
            time.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Expected wake_time in HH:MM format, e.g. 08:00") from exc
        if len(value) != 5:
            raise ValueError("Expected wake_time in HH:MM format, e.g. 08:00")
        return value
