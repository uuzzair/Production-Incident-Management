from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Severity = Literal["low", "medium", "high", "critical"]
IncidentStatus = Literal["open", "resolved"]


class Pagination(BaseModel):
    limit: int
    offset: int
    total: int


class IncidentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    created_by: str = Field(min_length=1, max_length=120)
    severity: Severity = "low"
    description: str = Field(min_length=1, max_length=5000)

    @field_validator("created_by")
    @classmethod
    def normalize_created_by(cls, value: str) -> str:
        return " ".join(value.split())


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    reporter_id: int | None = None
    created_by: str
    severity: Severity
    description: str
    status: IncidentStatus
    created_at: datetime


class IncidentUpdateCreate(BaseModel):
    message: str = Field(min_length=1, max_length=5000)


class IncidentUpdateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    incident_id: int
    message: str
    created_at: datetime


class IncidentDetailRead(IncidentRead):
    updates: list[IncidentUpdateRead] = Field(default_factory=list)


class IncidentListRead(BaseModel):
    items: list[IncidentRead]
    pagination: Pagination
