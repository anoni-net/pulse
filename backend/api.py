"""
Anoni.net Tor-Watcher API

This module provides a FastAPI application for storing and visualizing
daily observational data about Tor network activity. It exposes endpoints
for generating Vega-Lite compatible graphics and accessing network statistics.

The API is designed to be consumed by frontend applications and supports
CORS for cross-origin requests.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import psycopg
from fastapi import FastAPI, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware

from countries import COUNTRIES
from routers import summary, vega

logger = logging.getLogger(__name__)

TAG_META = [{"name": "vega", "description": "For Vega-Lite output graphics."}]


def _getenv(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is None:
        return None
    value = value.strip()
    return value or None


PG_CONN = _getenv("PG_CONN")

_cors_origins_raw = _getenv("CORS_ALLOW_ORIGINS", "")
CORS_ALLOW_ORIGINS = [o.strip() for o in (_cors_origins_raw or "").split(",") if o.strip()]

_cors_allow_credentials_raw = (_getenv("CORS_ALLOW_CREDENTIALS", "false") or "false").lower()
CORS_ALLOW_CREDENTIALS = _cors_allow_credentials_raw in {"1", "true", "yes", "on"}

app = FastAPI(
    title="Anoni.net Tor-Watcher API",
    description="Store daily observational datas.",
    version="2026.10.10.6",
    root_path="/api",
    docs_url="/readme",
    openapi_tags=TAG_META,
    contact={
        "name": "Anoni.net",
        "url": "https://anoni.net/",
        "email": "whisper@anoni.net",
    },
    license_info={
        "name": "GPL-3.0",
        "url": "https://github.com/anoni-net/docs/blob/main/asn_coverage/LICENSE",
    },
)

allow_origins = CORS_ALLOW_ORIGINS or ["*"]
# Wildcard origins cannot be used with credentials in browsers.
allow_credentials = CORS_ALLOW_CREDENTIALS if CORS_ALLOW_ORIGINS else False

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# Include routers
app.include_router(vega.router)
app.include_router(summary.router)


@app.get("/")
async def main():
    """
    Health check and API information endpoint.

    Returns:
        dict: A greeting message and link to API documentation.
    """
    return {"Hello": "world", "docs": "/api/readme"}


@app.get("/healthz")
async def healthz(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {"status": "ok", "version": app.version}


@app.get("/readyz")
async def readyz(response: Response):
    """
    Readiness probe. Connects to PostgreSQL on every call.

    Returns 503 when the database is unreachable so that container
    healthchecks and uptime monitors see the failure. A 200 here means the
    vega endpoints can actually serve data.
    """
    response.headers["Cache-Control"] = "no-store"
    if not PG_CONN:
        return {"status": "ok", "db": "skipped"}
    try:
        with psycopg.connect(PG_CONN, connect_timeout=3):
            pass
        return {"status": "ok", "db": "ok"}
    except Exception:
        logger.exception("DB readiness check failed")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "db": "error"}


FRESHNESS_SQL = """
    SELECT country, max(created_at)
    FROM relay_details
    WHERE created_at >= %(since)s
    GROUP BY country
"""


@app.get("/freshness")
async def freshness(response: Response, hours: int = Query(4, ge=1, le=168)):
    """
    Age of the latest snapshot for each collected country.

    The collector writes Onionoo's publish time, which already trails the
    wall clock by an hour or two, so the default threshold is four hours. A
    country is stale when its latest snapshot is older than that, or when it
    has none in the last eight days. Answers 200 either way; read `stale` to
    decide whether to alert. 503 only when the database is unreachable.

    Unlike readyz this catches the collector silently stopping while the API
    and the database stay healthy, which is how 2026-07-08 to 08-23 was lost.
    """
    response.headers["Cache-Control"] = "no-store"
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # created_at 是不帶時區的 UTC
    try:
        with psycopg.connect(PG_CONN, connect_timeout=5) as conn:
            rows = dict(conn.execute(FRESHNESS_SQL, {"since": now - timedelta(days=8)}).fetchall())
    except Exception:
        logger.exception("freshness query failed")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "db": "error"}
    countries = []
    for code in COUNTRIES:
        latest = rows.get(code)
        age = (now - latest).total_seconds() / 3600 if latest else None
        countries.append({
            "country": code,
            "latest": latest,
            "age_hours": None if age is None else round(age, 1),
            "stale": age is None or age > hours,
        })
    stale = [c["country"] for c in countries if c["stale"]]
    return {
        "status": "stale" if stale else "ok",
        "checked_at": now,
        "threshold_hours": hours,
        "stale": stale,
        "countries": countries,
    }
