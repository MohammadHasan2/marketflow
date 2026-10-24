
import os
from datetime import date
from typing import Annotated

import psycopg
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row


def get_connection():
    """Connect to Supabase PostgreSQL using configured environment variables."""
    try:
        database_url = os.getenv("SUPABASE_DB_URL")

        if database_url:
            return psycopg.connect(
                database_url,
                connect_timeout=8,
                row_factory=dict_row,
            )

        required = [
            "SUPABASE_DB_HOST",
            "SUPABASE_DB_USER",
            "SUPABASE_DB_PASSWORD",
        ]
        missing = [key for key in required if not os.getenv(key)]

        if missing:
            raise HTTPException(
                status_code=503,
                detail=f"Missing database configuration: {', '.join(missing)}",
            )

        return psycopg.connect(
            host=os.environ["SUPABASE_DB_HOST"],
            port=int(os.getenv("SUPABASE_DB_PORT", "5432")),
            dbname=os.getenv("SUPABASE_DB_NAME", "postgres"),
            user=os.environ["SUPABASE_DB_USER"],
            password=os.environ["SUPABASE_DB_PASSWORD"],
            sslmode=os.getenv("SUPABASE_DB_SSLMODE", "require"),
            connect_timeout=8,
            row_factory=dict_row,
        )

    except HTTPException:
        raise
    except (psycopg.Error, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Unable to connect to the configured database.",
        ) from exc


app = FastAPI(
    title="MarketFlow API",
    version="1.0.0",
    description="Read-only API for MarketFlow market data and pipeline monitoring.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://marketflow-6jmd.onrender.com"
    ],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Check API and database connectivity."""
    with get_connection() as connection:
        connection.execute("SELECT 1")

    return {"status": "healthy", "database": "connected"}


@app.get("/api/overview")
def overview():
    """Return dashboard metrics and the latest price for each symbol."""
    with get_connection() as connection:
        market = connection.execute(
            """
            SELECT
                COUNT(DISTINCT symbol) AS tracked_symbols,
                COUNT(*) AS price_records,
                MAX(trading_date) AS latest_trading_date,
                MAX(loaded_at) AS last_loaded_at
            FROM public.market_prices
            """
        ).fetchone()

        pipeline = connection.execute(
            """
            SELECT
                COUNT(*) AS total_runs,
                COUNT(*) FILTER (WHERE status = 'success') AS successful_runs,
                COUNT(*) FILTER (WHERE status = 'failed') AS failed_runs,
                MAX(started_at) AS last_run_at
            FROM public.pipeline_runs
            """
        ).fetchone()

        latest_prices = connection.execute(
            """
            SELECT DISTINCT ON (symbol)
                symbol,
                trading_date,
                open,
                high,
                low,
                close,
                volume,
                loaded_at
            FROM public.market_prices
            ORDER BY symbol, trading_date DESC
            """
        ).fetchall()

    return {
        "market": market,
        "pipeline": pipeline,
        "latest_prices": latest_prices,
    }


@app.get("/api/prices")
def get_prices(
    symbol: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
):
    """Return paginated market prices, optionally filtered by symbol."""
    offset = (page - 1) * page_size

    with get_connection() as connection:
        if symbol:
            count = connection.execute(
                """
                SELECT COUNT(*)
                FROM public.market_prices
                WHERE symbol = %s
                """,
                (symbol.upper(),),
            ).fetchone()["count"]

            rows = connection.execute(
                """
                SELECT
                    symbol, trading_date, open, high, low, close,
                    volume, source, loaded_at
                FROM public.market_prices
                WHERE symbol = %s
                ORDER BY trading_date DESC, symbol
                LIMIT %s OFFSET %s
                """,
                (symbol.upper(), page_size, offset),
            ).fetchall()
        else:
            count = connection.execute(
                "SELECT COUNT(*) FROM public.market_prices"
            ).fetchone()["count"]

            rows = connection.execute(
                """
                SELECT
                    symbol, trading_date, open, high, low, close,
                    volume, source, loaded_at
                FROM public.market_prices
                ORDER BY trading_date DESC, symbol
                LIMIT %s OFFSET %s
                """,
                (page_size, offset),
            ).fetchall()

    return {
        "data": rows,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_records": count,
            "total_pages": (count + page_size - 1) // page_size,
        },
    }


@app.get("/api/prices/{symbol}/history")
def get_price_history(
    symbol: str,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 365,
):
    """Return historical OHLCV data for one symbol."""
    conditions = ["symbol = %s"]
    params: list = [symbol.upper()]

    if start_date:
        conditions.append("trading_date >= %s")
        params.append(start_date)

    if end_date:
        conditions.append("trading_date <= %s")
        params.append(end_date)

    params.append(limit)

    query = f"""
        SELECT
            symbol, trading_date, open, high, low, close,
            volume, source, loaded_at
        FROM public.market_prices
        WHERE {" AND ".join(conditions)}
        ORDER BY trading_date DESC
        LIMIT %s
    """

    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()

    # Return oldest to newest, which is convenient for charts.
    rows.reverse()

    return {
        "symbol": symbol.upper(),
        "count": len(rows),
        "data": rows,
    }


@app.get("/api/pipeline-runs")
def get_pipeline_runs(
    status: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
):
    """Return paginated pipeline execution history."""
    allowed_statuses = {"running", "success", "failed"}

    if status and status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail="status must be running, success, or failed",
        )

    offset = (page - 1) * page_size

    with get_connection() as connection:
        if status:
            count = connection.execute(
                """
                SELECT COUNT(*)
                FROM public.pipeline_runs
                WHERE status = %s
                """,
                (status,),
            ).fetchone()["count"]

            rows = connection.execute(
                """
                SELECT
                    run_id, dag_id, status,
                    extracted_records, transformed_records, loaded_records,
                    started_at, finished_at, error_message
                FROM public.pipeline_runs
                WHERE status = %s
                ORDER BY started_at DESC
                LIMIT %s OFFSET %s
                """,
                (status, page_size, offset),
            ).fetchall()
        else:
            count = connection.execute(
                "SELECT COUNT(*) FROM public.pipeline_runs"
            ).fetchone()["count"]

            rows = connection.execute(
                """
                SELECT
                    run_id, dag_id, status,
                    extracted_records, transformed_records, loaded_records,
                    started_at, finished_at, error_message
                FROM public.pipeline_runs
                ORDER BY started_at DESC
                LIMIT %s OFFSET %s
                """,
                (page_size, offset),
            ).fetchall()

    return {
        "data": rows,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_records": count,
            "total_pages": (count + page_size - 1) // page_size,
        },
    }
