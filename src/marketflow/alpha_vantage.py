import os
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import requests


BASE_URL = "https://www.alphavantage.co/query"

PRICE_FIELDS = {
    "open": "1. open",
    "high": "2. high",
    "low": "3. low",
    "close": "4. close",
    "volume": "5. volume",
}


class MarketDataError(RuntimeError):
    """Raised when the market data provider returns unusable data."""


def get_api_key() -> str:
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()

    if not api_key or api_key == "your_actual_key_here":
        raise MarketDataError(
            "Set ALPHA_VANTAGE_API_KEY in your local .env file."
        )

    return api_key


def fetch_daily_prices(
    symbol: str,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Fetch the latest available daily OHLCV records for one symbol."""

    symbol = symbol.strip().upper()

    if not symbol:
        raise ValueError("Symbol cannot be empty.")

    timeout = int(os.getenv("MARKETFLOW_API_TIMEOUT", "30"))
    client = session or requests.Session()

    response = client.get(
        BASE_URL,
        params={
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "outputsize": "compact",
            "apikey": get_api_key(),
        },
        timeout=timeout,
    )
    response.raise_for_status()

    try:
        payload = response.json()
    except ValueError as exc:
        raise MarketDataError("Provider returned invalid JSON.") from exc

    # Alpha Vantage may return API errors or quota notices in HTTP 200
    # responses, so HTTP status alone is not sufficient.
    if "Error Message" in payload:
        raise MarketDataError(
            f"{symbol}: {payload['Error Message']}"
        )

    if "Note" in payload or "Information" in payload:
        message = payload.get("Note") or payload.get("Information")
        raise MarketDataError(
            f"{symbol}: provider notice or quota restriction: {message}"
        )

    time_series = payload.get("Time Series (Daily)")

    if not isinstance(time_series, dict) or not time_series:
        raise MarketDataError(
            f"{symbol}: daily time series is missing or empty."
        )

    records = []

    for trading_date, values in time_series.items():
        try:
            parsed_date = date.fromisoformat(trading_date)

            record = {
                "symbol": symbol,
                "trading_date": parsed_date.isoformat(),
                "open": Decimal(values[PRICE_FIELDS["open"]]),
                "high": Decimal(values[PRICE_FIELDS["high"]]),
                "low": Decimal(values[PRICE_FIELDS["low"]]),
                "close": Decimal(values[PRICE_FIELDS["close"]]),
                "volume": int(values[PRICE_FIELDS["volume"]]),
                "source": "alpha_vantage",
            }
        except (KeyError, ValueError, TypeError, InvalidOperation) as exc:
            raise MarketDataError(
                f"{symbol}: malformed market record for {trading_date}."
            ) from exc

        validate_record(record)
        records.append(record)

    records.sort(key=lambda item: item["trading_date"])
    return records


def validate_record(record: dict[str, Any]) -> None:
    """Reject invalid OHLCV records before they enter the pipeline."""

    prices = [
        record["open"],
        record["high"],
        record["low"],
        record["close"],
    ]

    if any(not value.is_finite() or value <= 0 for value in prices):
        raise MarketDataError(
            f"{record['symbol']} {record['trading_date']}: "
            "prices must be finite and positive."
        )

    if record["high"] < max(record["open"], record["close"]):
        raise MarketDataError(
            f"{record['symbol']} {record['trading_date']}: "
            "high is below open or close."
        )

    if record["low"] > min(record["open"], record["close"]):
        raise MarketDataError(
            f"{record['symbol']} {record['trading_date']}: "
            "low is above open or close."
        )

    if record["high"] < record["low"]:
        raise MarketDataError(
            f"{record['symbol']} {record['trading_date']}: "
            "high is below low."
        )

    if record["volume"] < 0:
        raise MarketDataError(
            f"{record['symbol']} {record['trading_date']}: "
            "volume cannot be negative."
        )


def fetch_configured_symbols() -> list[dict[str, Any]]:
    """Fetch configured symbols sequentially to limit API requests."""

    symbols = [
        symbol.strip().upper()
        for symbol in os.getenv("MARKET_SYMBOLS", "AAPL").split(",")
        if symbol.strip()
    ]

    if not symbols:
        raise MarketDataError("MARKET_SYMBOLS contains no symbols.")

    if len(set(symbols)) != len(symbols):
        raise MarketDataError("MARKET_SYMBOLS contains duplicates.")

    all_records = []

    for index, symbol in enumerate(symbols):
        if index:
            # Keep requests separated to reduce quota pressure.
            time.sleep(1)

        all_records.extend(fetch_daily_prices(symbol))

    return all_records