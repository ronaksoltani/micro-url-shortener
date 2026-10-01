"""FastAPI routes for link creation, redirects, and aggregate statistics."""

from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import Base, Click, ShortLink, engine, get_session
from .schemas import ShortenRequest, ShortenResponse, StatsResponse

SessionDep = Annotated[Session, Depends(get_session)]
BASE_URL = os.getenv("SHORTENER_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Micro URL Shortener",
    description="Shorten URLs, redirect visitors, and inspect aggregate click counts.",
    version="1.0.0",
    lifespan=lifespan,
)


def new_code() -> str:
    return secrets.token_urlsafe(6)


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/shorten", response_model=ShortenResponse, status_code=201, tags=["links"])
def shorten(payload: ShortenRequest, session: SessionDep) -> ShortenResponse:
    for attempt in range(5):
        code = payload.custom_code if attempt == 0 and payload.custom_code else new_code()
        if session.scalar(select(ShortLink).where(ShortLink.code == code)):
            if payload.custom_code:
                raise HTTPException(status_code=409, detail="That custom code is already in use.")
            continue
        link = ShortLink(code=code, target_url=str(payload.url))
        session.add(link)
        try:
            session.commit()
            session.refresh(link)
            return ShortenResponse(
                code=link.code,
                short_url=f"{BASE_URL}/{link.code}",
                target_url=link.target_url,
            )
        except IntegrityError:
            session.rollback()
            if payload.custom_code:
                raise HTTPException(status_code=409, detail="That custom code is already in use.")
    raise HTTPException(status_code=503, detail="Could not allocate a unique short code.")


@app.get("/{code}/stats", response_model=StatsResponse, tags=["analytics"])
def stats(code: str, session: SessionDep) -> StatsResponse:
    link = session.scalar(select(ShortLink).where(ShortLink.code == code))
    if link is None:
        raise HTTPException(status_code=404, detail="Short link not found.")
    total = session.scalar(select(func.count(Click.id)).where(Click.link_id == link.id)) or 0
    return StatsResponse(code=link.code, target_url=link.target_url, total_clicks=total)


@app.get("/{code}", response_class=RedirectResponse, include_in_schema=False)
def redirect(code: str, request: Request, session: SessionDep) -> Response:
    link = session.scalar(select(ShortLink).where(ShortLink.code == code))
    if link is None:
        raise HTTPException(status_code=404, detail="Short link not found.")
    session.add(
        Click(
            link_id=link.id,
            user_agent=request.headers.get("user-agent", "")[:512] or None,
            referrer=request.headers.get("referer", "")[:2048] or None,
        )
    )
    session.commit()
    return RedirectResponse(url=link.target_url, status_code=302)
