from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

from workbench.domain.types import Exchange


class ApiResponse(BaseModel):
    ok: bool
    data: Any | None = None
    error: dict | None = None


class HealthResponse(BaseModel):
    db_ok: bool
    providers: list[dict]
    now: str


class Instrument(BaseModel):
    symbol: str
    exchange: Exchange
    market: str = "CN_A"
    name: str | None = None
    industry: str | None = None


class TaskCreateRequest(BaseModel):
    type: str = Field(..., description="Task type")
    payload: dict = Field(default_factory=dict)


class TaskInfo(BaseModel):
    task_id: str
    type: str
    status: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    result: dict | None = None
