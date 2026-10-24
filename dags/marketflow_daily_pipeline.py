import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg2
from airflow import DAG
from airflow.operators.python import PythonOperator

from marketflow.alpha_vantage import (
    MarketDataError,
    fetch_configured_symbols,
    validate_record,
)


DATA_DIR = Path("/opt/airflow/data")
logger = logging.getLogger(__name__)


def get_run_file(context: dict[str, Any], prefix: str) -> Path:
    """Build a unique output filename for each Airflow run."""
    run_id = context["run_id"]
    safe_run_id = re.sub(r"[^a-zA-Z0-9_.-]", "_", run_id)
    return DATA_DIR / f"{prefix}_{safe_run_id}.json"


def serialize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Convert Decimal values to JSON-compatible strings."""
    return {
        key: str(value) if isinstance(value, Decimal) else value
        for key, value in record.items()
    }


def get_database_url() -> str:
    """Read the Supabase PostgreSQL connection string."""
    url = os.getenv("SUPABASE_DB_URL")

    if not url:
        raise RuntimeError("SUPABASE_DB_URL is not configured.")

    return url


def start_pipeline_audit(**context: Any) -> None:
    """Create or reset the audit row at the beginning of a run."""
    run_id = context["run_id"]
    dag_id = context["dag"].dag_id

    with psycopg2.connect(get_database_url()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO public.pipeline_runs (
                    run_id,
                    dag_id,
                    status,
                    started_at,
                    finished_at,
                    extracted_records,
                    transformed_records,
                    loaded_records,
                    error_message
                )
                VALUES (
                    %s, %s, 'running', NOW(), NULL, 0, 0, 0, NULL
                )
                ON CONFLICT (run_id) DO UPDATE SET
                    dag_id = EXCLUDED.dag_id,
                    status = 'running',
                    started_at = NOW(),
                    finished_at = NULL,
                    extracted_records = 0,
                    transformed_records = 0,
                    loaded_records = 0,
                    error_message = NULL
                """,
                (run_id, dag_id),
            )

    logger.info("Pipeline audit started: run_id=%s", run_id)


def mark_pipeline_failed(context: dict[str, Any]) -> None:
    """Record task failure without hiding the original Airflow error."""
    try:
        ti = context["ti"]
        run_id = context["run_id"]

        extracted_count = ti.xcom_pull(
            task_ids="extract_market_data"
        ) or 0

        transform_result = ti.xcom_pull(
            task_ids="validate_and_transform_market_data"
        ) or {}

        transformed_count = (
            transform_result.get("record_count", 0)
            if isinstance(transform_result, dict)
            else 0
        )

        exception = context.get("exception")
        error_message = str(exception or "Task failed")[:4000]

        with psycopg2.connect(get_database_url()) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE public.pipeline_runs
                    SET status = 'failed',
                        extracted_records = %s,
                        transformed_records = %s,
                        finished_at = NOW(),
                        error_message = %s
                    WHERE run_id = %s
                    """,
                    (
                        extracted_count,
                        transformed_count,
                        error_message,
                        run_id,
                    ),
                )

        logger.error(
            "Pipeline failure recorded: run_id=%s",
            run_id,
        )

    except Exception:
        logger.exception("Could not update pipeline failure audit")


def extract_market_data(**context: Any) -> int:
    """Extract market data and save the raw records to JSON."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    records = fetch_configured_symbols()

    if not records:
        raise MarketDataError("Extraction returned zero records.")

    output_path = get_run_file(context, "raw_market_data")

    payload = {
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "records": [
            serialize_record(record)
            for record in records
        ],
    }

    output_path.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    logger.info(
        "Extraction complete: records=%d file=%s",
        len(records),
        output_path.name,
    )

    return len(records)


def validate_and_transform(**context: Any) -> dict[str, int]:
    """Validate records, remove duplicate symbol/date pairs, and save JSON."""
    input_path = get_run_file(context, "raw_market_data")

    if not input_path.exists():
        raise FileNotFoundError(
            f"Expected extraction output: {input_path}"
        )

    payload = json.loads(
        input_path.read_text(encoding="utf-8")
    )
    records = payload.get("records", [])

    if not records:
        raise MarketDataError("No records found for validation.")

    normalized = []

    for item in records:
        record = {
            **item,
            "open": Decimal(str(item["open"])),
            "high": Decimal(str(item["high"])),
            "low": Decimal(str(item["low"])),
            "close": Decimal(str(item["close"])),
            "volume": int(item["volume"]),
        }

        validate_record(record)
        normalized.append(record)

    # Keep one record per symbol and trading date.
    unique_records = {}

    for record in normalized:
        key = (
            record["symbol"],
            record["trading_date"],
        )
        unique_records[key] = record

    transformed = sorted(
        unique_records.values(),
        key=lambda item: (
            item["symbol"],
            item["trading_date"],
        ),
    )

    duplicate_count = len(normalized) - len(transformed)
    output_path = get_run_file(context, "market_data")

    output = {
        "source": "alpha_vantage",
        "record_count": len(transformed),
        "duplicate_count": duplicate_count,
        "records": [
            serialize_record(record)
            for record in transformed
        ],
    }

    output_path.write_text(
        json.dumps(output, indent=2),
        encoding="utf-8",
    )

    logger.info(
        "Validation complete: input=%d output=%d duplicates=%d file=%s",
        len(normalized),
        len(transformed),
        duplicate_count,
        output_path.name,
    )

    return {
        "record_count": len(transformed),
        "duplicate_count": duplicate_count,
    }


def load_market_data(**context: Any) -> int:
    """Upsert transformed records and mark the pipeline successful."""
    input_path = get_run_file(context, "market_data")

    if not input_path.exists():
        raise FileNotFoundError(
            f"Missing transformed file: {input_path}"
        )

    payload = json.loads(
        input_path.read_text(encoding="utf-8")
    )
    records = payload.get("records", [])

    if not records:
        raise MarketDataError("No transformed records to load.")

    rows = [
        (
            record["symbol"],
            record["trading_date"],
            record["open"],
            record["high"],
            record["low"],
            record["close"],
            record["volume"],
            record.get("source", "alpha_vantage"),
        )
        for record in records
    ]

    ti = context["ti"]

    extracted_count = ti.xcom_pull(
        task_ids="extract_market_data"
    ) or 0

    transform_result = ti.xcom_pull(
        task_ids="validate_and_transform_market_data"
    ) or {}

    transformed_count = transform_result.get(
        "record_count", 0
    )

    connection = psycopg2.connect(get_database_url())

    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO public.market_prices (
                        symbol,
                        trading_date,
                        open,
                        high,
                        low,
                        close,
                        volume,
                        source
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, trading_date)
                    DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        source = EXCLUDED.source,
                        loaded_at = NOW()
                    """,
                    rows,
                )

                cursor.execute(
                    """
                    UPDATE public.pipeline_runs
                    SET status = 'success',
                        extracted_records = %s,
                        transformed_records = %s,
                        loaded_records = %s,
                        finished_at = NOW(),
                        error_message = NULL
                    WHERE run_id = %s
                    """,
                    (
                        extracted_count,
                        transformed_count,
                        len(rows),
                        context["run_id"],
                    ),
                )

        logger.info(
            "Supabase load complete: records=%d run_id=%s",
            len(rows),
            context["run_id"],
        )

    finally:
        connection.close()

    return len(rows)


with DAG(
    dag_id="marketflow_daily_pipeline",
    description="Daily financial market data ingestion and validation",
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    schedule="@daily",
    catchup=False,
    default_args={
        "owner": "marketflow",
        "retries": 2,
        "retry_delay": timedelta(minutes=1),
        "execution_timeout": timedelta(minutes=5),
        "on_failure_callback": mark_pipeline_failed,
    },
    max_active_runs=1,
    tags=["marketflow", "finance", "data-engineering"],
) as dag:

    audit_task = PythonOperator(
        task_id="start_pipeline_audit",
        python_callable=start_pipeline_audit,
    )

    extract_task = PythonOperator(
        task_id="extract_market_data",
        python_callable=extract_market_data,
    )

    validate_task = PythonOperator(
        task_id="validate_and_transform_market_data",
        python_callable=validate_and_transform,
    )

    load_task = PythonOperator(
        task_id="load_market_data_to_supabase",
        python_callable=load_market_data,
    )

    audit_task >> extract_task >> validate_task >> load_task