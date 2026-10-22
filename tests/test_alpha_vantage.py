from decimal import Decimal

import pytest

from marketflow import alpha_vantage as av


class FakeResponse:
    def __init__(self, payload=None, json_error=False):
        self.payload = payload
        self.json_error = json_error
        self.request_args = None

    def raise_for_status(self):
        pass

    def json(self):
        if self.json_error:
            raise ValueError("Invalid JSON")
        return self.payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.call = None

    def get(self, url, **kwargs):
        self.call = (url, kwargs)
        return self.response


def valid_record(**overrides):
    record = {
        "symbol": "AAPL",
        "trading_date": "2026-10-21",
        "open": Decimal("100"),
        "high": Decimal("110"),
        "low": Decimal("90"),
        "close": Decimal("105"),
        "volume": 1000,
        "source": "alpha_vantage",
    }
    record.update(overrides)
    return record


def test_fetch_daily_prices_parses_and_sorts_records(monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")

    payload = {
        "Time Series (Daily)": {
            "2026-10-21": {
                "1. open": "100",
                "2. high": "110",
                "3. low": "90",
                "4. close": "105",
                "5. volume": "1000",
            },
            "2026-10-20": {
                "1. open": "95",
                "2. high": "105",
                "3. low": "85",
                "4. close": "100",
                "5. volume": "900",
            },
        }
    }
    session = FakeSession(FakeResponse(payload))

    records = av.fetch_daily_prices(" aapl ", session=session)

    assert len(records) == 2
    assert records[0]["trading_date"] == "2026-10-20"
    assert records[1]["trading_date"] == "2026-10-21"
    assert records[1]["symbol"] == "AAPL"
    assert records[1]["close"] == Decimal("105")
    assert records[1]["volume"] == 1000

    url, kwargs = session.call
    assert url == av.BASE_URL
    assert kwargs["params"]["symbol"] == "AAPL"
    assert kwargs["params"]["apikey"] == "test-key"


def test_missing_api_key_fails(monkeypatch):
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)

    with pytest.raises(av.MarketDataError, match="ALPHA_VANTAGE_API_KEY"):
        av.get_api_key()


@pytest.mark.parametrize(
    "payload",
    [
        {"Note": "API call frequency exceeded"},
        {"Information": "Daily request limit reached"},
    ],
)
def test_provider_quota_notice_fails(monkeypatch, payload):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")
    session = FakeSession(FakeResponse(payload))

    with pytest.raises(av.MarketDataError, match="quota restriction"):
        av.fetch_daily_prices("AAPL", session=session)


def test_provider_error_fails(monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")
    session = FakeSession(
        FakeResponse({"Error Message": "Invalid symbol"})
    )

    with pytest.raises(av.MarketDataError, match="Invalid symbol"):
        av.fetch_daily_prices("AAPL", session=session)


def test_invalid_json_fails(monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")
    session = FakeSession(FakeResponse(json_error=True))

    with pytest.raises(av.MarketDataError, match="invalid JSON"):
        av.fetch_daily_prices("AAPL", session=session)


def test_missing_time_series_fails(monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")
    session = FakeSession(FakeResponse({"Meta Data": {}}))

    with pytest.raises(av.MarketDataError, match="missing or empty"):
        av.fetch_daily_prices("AAPL", session=session)


def test_empty_symbol_fails():
    with pytest.raises(ValueError, match="Symbol cannot be empty"):
        av.fetch_daily_prices("  ")


def test_valid_record_passes_validation():
    av.validate_record(valid_record())


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"close": Decimal("-1")}, "finite and positive"),
        ({"high": Decimal("99")}, "high is below"),
        ({"low": Decimal("101")}, "low is above"),
        ({"volume": -1}, "volume cannot be negative"),
    ],
)
def test_invalid_records_fail_validation(overrides, message):
    with pytest.raises(av.MarketDataError, match=message):
        av.validate_record(valid_record(**overrides))


def test_duplicate_configured_symbols_fail(monkeypatch):
    monkeypatch.setenv("MARKET_SYMBOLS", "AAPL,aapl")

    with pytest.raises(av.MarketDataError, match="duplicates"):
        av.fetch_configured_symbols()


def test_empty_configured_symbols_fail(monkeypatch):
    monkeypatch.setenv("MARKET_SYMBOLS", " , ")

    with pytest.raises(av.MarketDataError, match="no symbols"):
        av.fetch_configured_symbols()


def test_configured_symbols_are_normalized(monkeypatch):
    monkeypatch.setenv("MARKET_SYMBOLS", " aapl , msft ")
    monkeypatch.setattr(av.time, "sleep", lambda _: None)

    calls = []

    def fake_fetch(symbol):
        calls.append(symbol)
        return [{"symbol": symbol}]

    monkeypatch.setattr(av, "fetch_daily_prices", fake_fetch)

    records = av.fetch_configured_symbols()

    assert calls == ["AAPL", "MSFT"]
    assert [record["symbol"] for record in records] == ["AAPL", "MSFT"]
