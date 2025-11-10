# 1_data_collection.py
# This script will download the latest 10-K (annual) and 10-Q (quarterly) filings for Apple, Microsoft, and NVIDIA.

from sec_edgar_downloader import Downloader
import os

def download_sec_filings():
    """
    Initializes the downloader and fetches the latest SEC filings for specified tickers.
    """
    save_path = "sec_filings"
    if not os.path.exists(save_path):
        os.makedirs(save_path)
        print(f"Created directory: {save_path}")

    dl = Downloader("Harshith Chejerla", "harshith.chejerla@gmail.com", save_path)
    
    # List of tickers for the companies we are interested in as of now
    tickers = ["AAPL", "MSFT", "NVDA"]

    print("Starting download of SEC filings...")

    for ticker in tickers:
        try:
            print(f"Downloading 10-K filings for {ticker}...")
            dl.get("10-K", ticker, limit=5)
            
            print(f"Downloading 10-Q filings for {ticker}...")
            dl.get("10-Q", ticker, limit=5)
            
            print(f"Successfully downloaded filings for {ticker}.")
        except Exception as e:
            print(f"Could not download filings for {ticker}. Error: {e}")

    print("\nAll downloads complete.")
    print(f"Filings are saved in the '{save_path}' directory.")


if __name__ == "__main__":
    download_sec_filings()


# END