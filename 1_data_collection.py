"""Download annual and quarterly SEC submissions, with an optional ticker filter."""

import argparse
from datetime import date
import os
from pathlib import Path

from dotenv import load_dotenv
from sec_edgar_downloader import Downloader

DEFAULT_ROOT = Path(__file__).resolve().parent / "sec_filings"


def download_sec_filings(tickers=("AAPL", "MSFT", "NVDA"), limit=5, save_path=DEFAULT_ROOT):
    if limit < 1:
        raise ValueError("The filing limit must be positive.")
    load_dotenv()
    save_path = Path(save_path).resolve()
    save_path.mkdir(parents=True, exist_ok=True)
    downloader = Downloader(
        os.getenv("SEC_COMPANY_NAME", "Harshith Chejerla"),
        os.getenv("SEC_EMAIL", "harshith.chejerla@gmail.com"),
        save_path,
    )
    counts = {}
    for ticker in sorted({ticker.upper() for ticker in tickers}):
        for filing_type in ("10-K", "10-Q"):
            print(f"Downloading latest {limit} {filing_type} filings for {ticker}...", flush=True)
            count = downloader.get(
                filing_type, ticker, limit=limit, before=date.today(), include_amends=False
            )
            counts[f"{ticker}/{filing_type}"] = count
            if count != limit:
                raise RuntimeError(
                    f"Only {count}/{limit} {ticker} {filing_type} filings available locally. "
                    "Check download errors or request a smaller limit."
                )
    print(f"Complete: {sum(counts.values())} filings downloaded or already present in {save_path}")
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="+", default=["AAPL", "MSFT", "NVDA"])
    parser.add_argument("--limit", type=int, default=5, help="Filings per ticker and form")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    download_sec_filings(args.tickers, args.limit, args.output_dir)
