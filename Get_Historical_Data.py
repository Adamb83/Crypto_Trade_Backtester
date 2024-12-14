# Get_Historical_Data.py
# Copyright (C) 2024 Adam P Baguley
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License Version 3 as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License Version 3 for more details.
#https://www.gnu.org/licenses/.

import requests
import pandas as pd
from time import sleep
from pytz import UTC

# Binance API details
INTERVAL = "4h"
MAX_LIMIT = 1000

# Output CSV base directory
OUTPUT_DIR = "D:/Historic_prices/"

# Moving average and RSI parameters
MA_LENGTHS = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100, 105, 110, 120, 240]
RSI_PERIODS = [3, 7, 14, 21]

def fetch_top_usdt_pairs(limit=300):
    """Fetch the top USDT pairs by volume."""
    url = "https://api.binance.com/api/v3/ticker/24hr"
    response = requests.get(url)
    if response.status_code == 200:
        tickers = response.json()
        usdt_pairs = [
            ticker["symbol"] for ticker in tickers
            if "USDT" in ticker["symbol"] and not ticker["symbol"].endswith("DOWNUSDT") and not ticker["symbol"].endswith("UPUSDT")
        ]
        return usdt_pairs[:limit]
    else:
        raise Exception(f"Failed to fetch tickers: {response.status_code}, {response.text}")

def fetch_historical_data(symbol, interval, start_time=None, end_time=None):
    """Fetch historical data from Binance API."""
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": MAX_LIMIT,
        "startTime": int(start_time.timestamp() * 1000) if start_time else None,
        "endTime": int(end_time.timestamp() * 1000) if end_time else None
    }

    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Failed to fetch data: {response.status_code}, {response.text}")

def process_data(raw_data):
    """Convert raw data to a DataFrame and process timestamps."""
    columns = [
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "number_of_trades",
        "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"
    ]
    df = pd.DataFrame(raw_data, columns=columns)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)

    # Convert numeric columns
    numeric_cols = ["open", "high", "low", "close", "volume", "quote_asset_volume",
                    "taker_buy_base_volume", "taker_buy_quote_volume"]
    df[numeric_cols] = df[numeric_cols].astype(float)

    return df.drop(columns=["ignore"], errors="ignore")

def calculate_indicators(data):
    """Calculate SMA, EMA, and RSI indicators."""
    # Calculate SMAs and EMAs
    for length in MA_LENGTHS:
        data[f"sma_{length}"] = data["close"].rolling(window=length).mean()
        data[f"ema_{length}"] = data["close"].ewm(span=length, adjust=False).mean()

    # Calculate RSIs
    for period in RSI_PERIODS:
        delta = data["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
        rs = gain / loss
        data[f"rsi_{period}"] = 100 - (100 / (1 + rs))

    return data

def save_to_csv(data, symbol, interval):
    """Save processed data to a CSV file."""
    filename = f"{OUTPUT_DIR}historic_{symbol.lower()}_{interval}.csv"
    data.to_csv(filename, index=False)
    print(f"[INFO] Data saved to {filename}")

def fetch_and_save_full_history(symbol, interval):
    """Fetch full historical data and save with indicators."""
    print(f"[INFO] Fetching full history for {symbol} at {interval} interval...")
    all_data = []
    end_time = None

    while True:
        try:
            raw_data = fetch_historical_data(symbol, interval, end_time=end_time)
            if not raw_data or len(raw_data) == 1:  # Break if no data or repetitive single-row fetch
                print("[INFO] No more data to fetch. Ending.")
                break

            df = process_data(raw_data)
            all_data.append(df)

            # Update end_time to the earliest timestamp in the current batch minus 1 ms
            end_time = df["timestamp"].iloc[0] - pd.Timedelta(milliseconds=1)

            print(f"[INFO] Fetched {len(df)} rows, continuing...")
            sleep(1)  # Prevent rate-limiting
        except Exception as e:
            print(f"[ERROR] {e}")
            break

    if all_data:
        final_data = pd.concat(all_data).drop_duplicates(subset="timestamp").sort_values(by="timestamp")
        final_data = calculate_indicators(final_data)
        save_to_csv(final_data, symbol, interval)
    else:
        print("[INFO] No data fetched.")


def main():
    try:
        usdt_pairs = fetch_top_usdt_pairs(limit=300)
        print(f"[INFO] Fetched {len(usdt_pairs)} USDT pairs.")
        for pair in usdt_pairs:
            fetch_and_save_full_history(pair, INTERVAL)
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__ == "__main__":
    main()
#This Works 