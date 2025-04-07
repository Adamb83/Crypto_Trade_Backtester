import requests
import pandas as pd
from datetime import datetime
import time
import os

# Set the save directory
SAVE_DIR = "D:/Historic_prices/hour/"  # Replace with your desired path

# Ensure the directory exists
os.makedirs(SAVE_DIR, exist_ok=True)

# Fetch all available USDT spot trading pairs
def fetch_all_spot_pairs():
    url = "https://api.binance.com/api/v3/exchangeInfo"
    response = requests.get(url).json()
    spot_pairs = [
        symbol["symbol"]
        for symbol in response["symbols"]
        if symbol["status"] == "TRADING" and symbol["quoteAsset"] == "USDT"
    ]
    return spot_pairs

# Fetch historical 1-hour data for a given symbol between start_date and end_date
def fetch_historical_data(symbol, start_date, end_date, interval="1h"):
    url = "https://api.binance.com/api/v3/klines"
    # Convert dates to milliseconds timestamps
    start_time = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
    end_time = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
    
    all_data = []
    while start_time < end_time:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": start_time,
            "limit": 1000,
        }
        response = requests.get(url, params=params).json()
        if isinstance(response, list) and response:
            all_data.extend(response)
            start_time = response[-1][0] + 1  # Move to the next batch
        else:
            break  # No more data
        time.sleep(0.1)  # Avoid hitting rate limits

    # Convert to DataFrame with Binance's kline columns
    df = pd.DataFrame(all_data, columns=[
        "Open time", "Open", "High", "Low", "Close", "Volume",
        "Close time", "Quote asset volume", "Number of trades",
        "Taker buy base asset volume", "Taker buy quote asset volume", "Ignore"
    ])
    # Convert "Open time" to datetime
    df["Open time"] = pd.to_datetime(df["Open time"], unit="ms")
    return df

# Download historical data for all USDT pairs in 1-hour timeframe
def download_data_for_usdt_pairs():
    pairs = fetch_all_spot_pairs()
    start_date = "2017-01-01"  # Binance's earliest possible date
    end_date = datetime.now().strftime("%Y-%m-%d")  # Today's date

    for pair in pairs:
        print(f"Downloading data for {pair} (1-hour timeframe)...")
        try:
            df = fetch_historical_data(symbol=pair, start_date=start_date, end_date=end_date, interval="1h")
            if not df.empty:
                file_path = os.path.join(SAVE_DIR, f"{pair}_1h_data.csv")
                df.to_csv(file_path, index=False)
                print(f"Data for {pair} saved to {file_path}.")
            else:
                print(f"No data available for {pair}.")
        except Exception as e:
            print(f"Error downloading data for {pair}: {e}")
        time.sleep(1)  # Pause to avoid rate limits

if __name__ == "__main__":
    print(f"Data will be saved to: {SAVE_DIR}")
    download_data_for_usdt_pairs()
