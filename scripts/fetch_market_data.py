import json
import logging
from pathlib import Path

from dotenv import load_dotenv

from src.market_data import fetch_configured_symbols


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def main() -> None:
    records = fetch_configured_symbols()

    output_dir = PROJECT_ROOT / "data"
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / "market_data.json"

    output_file.write_text(
        json.dumps(
            [
                {
                    **record,
                    **{
                        key: str(value)
                        for key, value in record.items()
                        if key in {"open", "high", "low", "close"}
                    },
                }
                for record in records
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    logging.info("Records retrieved: %s", len(records))
    logging.info("Symbols: %s", sorted({r["symbol"] for r in records}))
    logging.info(
        "Date range: %s to %s",
        records[0]["trading_date"],
        records[-1]["trading_date"],
    )
    logging.info("Output: %s", output_file)


if __name__ == "__main__":
    main()