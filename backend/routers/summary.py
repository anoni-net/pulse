"""
Summary endpoint for the Pulse page on anoni.net.

One request per country returns everything the page draws: daily totals, the
daily spread of Tor release series and of full versions, and the ASNs, versions
and flags of the most recent snapshot.

Each day is represented by its last hourly snapshot instead of every relay seen
during the day. The vega endpoints aggregate a country's whole history on every
call; for the United States the flags query took about 52 seconds in 2026-10.
Reading one snapshot per day over a bounded window keeps every country under a
second, which matters because the site rebuilds the page hourly.
"""

from datetime import date, datetime

from cachetools import TTLCache
from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel

from pgdb import PGConn
from routers.vega import Country

CACHE_TTL_SECONDS = 300

_cache: TTLCache = TTLCache(maxsize=64, ttl=CACHE_TTL_SECONDS)


def cache_headers(response: Response) -> None:
    """Advertise the same TTL the in-process cache uses."""
    response.headers["Cache-Control"] = f"public, max-age={CACHE_TTL_SECONDS}"


router = APIRouter(
    prefix="/summary",
    tags=["summary"],
    dependencies=[Depends(cache_headers)],
)


class Daily(BaseModel):
    """Totals from the last snapshot of one day."""

    date: date
    snapshot: datetime
    running: int
    stopped: int
    bandwidth: int  # observed bandwidth of running relays, bytes per second
    asns: int  # distinct ASNs among running relays
    guard: int  # running relays with guard_probability > 0
    middle: int
    exit: int
    # 運作中中繼的 consensus_weight_fraction 加總，占整個 Tor 網路的比例（0 到 1）。
    # 2026-10 之前的快照沒有這個欄位，是 None
    weight: float | None = None


class SeriesCount(BaseModel):
    """Running relays on one Tor release series (for example 0.4.9) on one day."""

    date: date
    series: str
    count: int


class VersionDaily(BaseModel):
    """Running relays on one full Tor version (for example 0.4.9.14) on one day."""

    date: date
    version: str
    count: int


class AsnCount(BaseModel):
    asn: str
    as_name: str
    count: int
    bandwidth: int


class VersionCount(BaseModel):
    version: str
    count: int


class FlagCount(BaseModel):
    flag: str
    count: int


class Latest(BaseModel):
    """Running relays in the most recent snapshot."""

    snapshot: datetime | None
    asns: list[AsnCount]
    versions: list[VersionCount]
    flags: list[FlagCount]


class Summary(BaseModel):
    country: str
    days: int
    daily: list[Daily]
    series: list[SeriesCount]
    versions: list[VersionDaily]
    latest: Latest


# The last snapshot of each day inside the window. Uses the
# (country, date(created_at)) index, so it never touches older history.
SNAPS = """
    WITH snaps AS (
        SELECT date(created_at) AS dt, max(created_at) AS ts
        FROM relay_details
        WHERE country = %(country)s AND date(created_at) >= current_date - %(days)s
        GROUP BY 1
    )
"""

DAILY_SQL = SNAPS + """
    SELECT s.dt, s.ts,
           count(*) FILTER (WHERE r.running),
           count(*) FILTER (WHERE NOT r.running),
           coalesce(sum(r.observed_bandwidth) FILTER (WHERE r.running), 0),
           count(DISTINCT r.asn) FILTER (WHERE r.running),
           count(*) FILTER (WHERE r.running AND r.guard_probability > 0),
           count(*) FILTER (WHERE r.running AND r.middle_probability > 0),
           count(*) FILTER (WHERE r.running AND r.exit_probability > 0),
           sum(r.consensus_weight_fraction) FILTER (WHERE r.running)
    FROM snaps s
    JOIN relay_details r ON r.created_at = s.ts AND r.country = %(country)s
    GROUP BY s.dt, s.ts
    ORDER BY s.dt
"""

SERIES_SQL = SNAPS + """
    SELECT s.dt,
           split_part(r.version, '.', 1) || '.' || split_part(r.version, '.', 2)
               || '.' || split_part(r.version, '.', 3) AS series,
           count(*)
    FROM snaps s
    JOIN relay_details r ON r.created_at = s.ts AND r.country = %(country)s
    WHERE r.running AND r.version IS NOT NULL
    GROUP BY 1, 2
    ORDER BY 1, 2
"""

VERSIONS_SQL = SNAPS + """
    SELECT s.dt, r.version, count(*)
    FROM snaps s
    JOIN relay_details r ON r.created_at = s.ts AND r.country = %(country)s
    WHERE r.running AND r.version IS NOT NULL
    GROUP BY 1, 2
    ORDER BY 1, 2
"""

LATEST_TS_SQL = """
    SELECT max(created_at) FROM relay_details
    WHERE country = %(country)s AND date(created_at) >= current_date - %(days)s
"""

LATEST_ASN_SQL = """
    SELECT asn, max(as_name), count(*), coalesce(sum(observed_bandwidth), 0)
    FROM relay_details
    WHERE created_at = %(ts)s AND country = %(country)s AND running
    GROUP BY asn
    ORDER BY 3 DESC, 4 DESC, 1
"""

LATEST_VERSION_SQL = """
    SELECT version, count(*)
    FROM relay_details
    WHERE created_at = %(ts)s AND country = %(country)s AND running AND version IS NOT NULL
    GROUP BY 1
    ORDER BY 2 DESC, 1 DESC
"""

LATEST_FLAG_SQL = """
    SELECT flag, count(*)
    FROM relay_details, unnest(flags) AS flag
    WHERE created_at = %(ts)s AND country = %(country)s AND running
    GROUP BY 1
    ORDER BY 2 DESC, 1
"""


def build_summary(country: str, days: int) -> Summary:
    params = {"country": country, "days": days}
    with PGConn() as pg_conn:
        cur = pg_conn.cur
        daily = [
            Daily(date=r[0], snapshot=r[1], running=r[2], stopped=r[3], bandwidth=r[4],
                  asns=r[5], guard=r[6], middle=r[7], exit=r[8], weight=r[9])
            for r in cur.execute(DAILY_SQL, params).fetchall()
        ]
        series = [
            SeriesCount(date=r[0], series=r[1], count=r[2])
            for r in cur.execute(SERIES_SQL, params).fetchall()
        ]
        versions = [
            VersionDaily(date=r[0], version=r[1], count=r[2])
            for r in cur.execute(VERSIONS_SQL, params).fetchall()
        ]
        ts = cur.execute(LATEST_TS_SQL, params).fetchone()[0]
        latest = Latest(snapshot=ts, asns=[], versions=[], flags=[])
        if ts is not None:
            params["ts"] = ts
            latest.asns = [
                AsnCount(asn=r[0] or "", as_name=r[1] or "", count=r[2], bandwidth=r[3])
                for r in cur.execute(LATEST_ASN_SQL, params).fetchall()
            ]
            latest.versions = [
                VersionCount(version=r[0], count=r[1])
                for r in cur.execute(LATEST_VERSION_SQL, params).fetchall()
            ]
            latest.flags = [
                FlagCount(flag=r[0], count=r[1])
                for r in cur.execute(LATEST_FLAG_SQL, params).fetchall()
            ]
    return Summary(country=country, days=days, daily=daily, series=series, versions=versions,
                   latest=latest)


@router.get("")
async def summary(country: Country, days: int = Query(60, ge=7, le=365)) -> Summary:
    """
    Everything the anoni.net Pulse page draws for one country.

    Args:
        country: Country code
        days: How many recent days to include (7 to 365, default 60)

    Returns:
        Daily totals from the last snapshot of each day, the daily spread of
        release series, and the ASNs, versions and flags of the latest snapshot.
    """
    key = (country.value, days)
    if key not in _cache:
        _cache[key] = build_summary(country.value, days)
    return _cache[key]
