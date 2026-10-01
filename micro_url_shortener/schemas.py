"""Validated request and response models."""

from __future__ import annotations

from pydantic import AnyHttpUrl, BaseModel, Field


class ShortenRequest(BaseModel):
    url: AnyHttpUrl
    custom_code: str | None = Field(
        default=None,
        min_length=4,
        max_length=24,
        pattern=r"^[A-Za-z0-9_-]+$",
    )


class ShortenResponse(BaseModel):
    code: str
    short_url: str
    target_url: str


class StatsResponse(BaseModel):
    code: str
    target_url: str
    total_clicks: int
