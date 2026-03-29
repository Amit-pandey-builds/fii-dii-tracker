# FII/DII Data Tracker - Built by Amit Pandey

import logging
import sqlite3
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB_PATH = "fii_dii.db"
NSE_BASE_URL = "https://www.nseindia.com"
NSE_API_URL = "https://www.nseindia.com/api/fiidiiTradeReact"
IST = ZoneInfo("Asia/Kolkata")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fii_dii_data (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                date       TEXT    UNIQUE NOT NULL,
                fii_buy    REAL,
                fii_sell   REAL,
                fii_net    REAL,
                dii_buy    REAL,
                dii_sell   REAL,
                dii_net    REAL,
                fetched_at TEXT
            )
        """)


def upsert_record(
    trade_date: str,
    fii_buy: Optional[float],
    fii_sell: Optional[float],
    fii_net: Optional[float],
    dii_buy: Optional[float],
    dii_sell: Optional[float],
    dii_net: Optional[float],
    fetched_at: str,
) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO fii_dii_data
                (date, fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                fii_buy    = excluded.fii_buy,
                fii_sell   = excluded.fii_sell,
                fii_net    = excluded.fii_net,
                dii_buy    = excluded.dii_buy,
                dii_sell   = excluded.dii_sell,
                dii_net    = excluded.dii_net,
                fetched_at = excluded.fetched_at
            """,
            (trade_date, fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net, fetched_at),
        )


def query_by_date(trade_date: str) -> Optional[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM fii_dii_data WHERE date = ?", (trade_date,)
        ).fetchone()


def query_recent(days: int) -> list[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM fii_dii_data ORDER BY date DESC LIMIT ?", (days,)
        ).fetchall()


# ---------------------------------------------------------------------------
# NSE client
# ---------------------------------------------------------------------------

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    # Accept-Encoding intentionally omitted — lets httpx handle
    # decompression automatically, avoiding raw gzip byte errors
    "Referer": "https://www.nseindia.com/",
    "X-Requested-With": "XMLHttpRequest",
}


def _to_float(value: str) -> Optional[float]:
    """Convert NSE string value (may contain commas) to float."""
    try:
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


async def _fetch_raw() -> list[dict]:
    """Fetch raw JSON from NSE, seeding cookies via a homepage visit first."""
    async with httpx.AsyncClient(
        headers=NSE_HEADERS,
        follow_redirects=True,
        timeout=30,
    ) as client:
        # Seed session cookies — NSE blocks requests without a prior visit
        await client.get(NSE_BASE_URL)
        response = await client.get(NSE_API_URL)
        response.raise_for_status()
        return response.json()


def _parse(raw: list[dict]) -> dict:
    """Extract FII and DII figures from the raw NSE response."""
    result: dict = {}
    for item in raw:
        category = item.get("category", "").upper()
        entry = {
            "buy":  _to_float(item.get("buyValue")),
            "sell": _to_float(item.get("sellValue")),
            "net":  _to_float(item.get("netValue")),
        }
        if "FII" in category or "FPI" in category:
            result["fii"] = entry
        elif "DII" in category:
            result["dii"] = entry
    return result


async def fetch_and_store() -> None:
    """Fetch today's FII/DII data from NSE and persist it."""
    logger.info("Fetching FII/DII data from NSE …")
    try:
        raw = await _fetch_raw()
        data = _parse(raw)

        fii = data.get("fii", {})
        dii = data.get("dii", {})
        trade_date = date.today().isoformat()
        fetched_at = datetime.now(IST).isoformat()

        upsert_record(
            trade_date,
            fii.get("buy"),  fii.get("sell"),  fii.get("net"),
            dii.get("buy"),  dii.get("sell"),  dii.get("net"),
            fetched_at,
        )
        logger.info("Stored FII/DII data for %s", trade_date)
    except Exception as exc:
        logger.error("Failed to fetch/store data: %s", exc)


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

scheduler = AsyncIOScheduler(timezone=IST)


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.add_job(
        fetch_and_store,
        CronTrigger(hour=18, minute=30, timezone=IST),
        id="daily_fetch",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — daily fetch at 18:30 IST")
    yield
    scheduler.shutdown()


app = FastAPI(title="FII/DII Tracker", version="1.0.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class DayData(BaseModel):
    date: str
    fii_buy: Optional[float] = None
    fii_sell: Optional[float] = None
    fii_net: Optional[float] = None
    dii_buy: Optional[float] = None
    dii_sell: Optional[float] = None
    dii_net: Optional[float] = None
    fetched_at: Optional[str] = None


def _row_to_model(row: sqlite3.Row) -> DayData:
    return DayData(
        date=row["date"],
        fii_buy=row["fii_buy"],
        fii_sell=row["fii_sell"],
        fii_net=row["fii_net"],
        dii_buy=row["dii_buy"],
        dii_sell=row["dii_sell"],
        dii_net=row["dii_net"],
        fetched_at=row["fetched_at"],
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/today", response_model=DayData, summary="Today's FII/DII data")
async def get_today():
    """Return today's FII and DII cash market figures.
    If no record exists yet, a live fetch from NSE is attempted first."""
    today = date.today().isoformat()
    row = query_by_date(today)
    if row is None:
        await fetch_and_store()
        row = query_by_date(today)
    if row is None:
        raise HTTPException(status_code=404, detail="No data available for today")
    return _row_to_model(row)


@app.get("/history", response_model=list[DayData], summary="Historical FII/DII data")
async def get_history(
    days: int = Query(default=30, ge=1, le=365, description="Number of past days to return"),
):
    """Return the last *days* records ordered by date descending."""
    rows = query_recent(days)
    return [_row_to_model(r) for r in rows]


@app.post("/fetch", summary="Manually trigger a data fetch")
async def manual_fetch():
    """Force an immediate fetch from NSE and store the result."""
    await fetch_and_store()
    return {"status": "ok", "message": "Data fetched and stored"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
