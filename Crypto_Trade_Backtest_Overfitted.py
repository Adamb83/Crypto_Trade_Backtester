# Crypto_Trade_Backtest_Overfitted.py
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


import pandas as pd
from itertools import product
import os

# Input CSV file with historical data
INPUT_CSV = "D:/Process_wallet_data/historic_btc_4hr.csv"

# Output directory for trade logs and performance summary
OUTPUT_DIR = "D:/Process_wallet_data/"

# Moving average lengths to test
MA_LENGTHS = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100, 105, 110, 120, 240]

def calculate_ma(df, ma_type, length):
    if ma_type == "sma":
        return df["close"].rolling(window=length).mean()
    elif ma_type == "ema":
        return df["close"].ewm(span=length, adjust=False).mean()

def backtest_strategy(data, short_ma_type, short_ma_length, long_ma_type, long_ma_length):
    """Run the backtesting logic for a given moving average combination."""
    data[f"short_ma"] = calculate_ma(data, short_ma_type, short_ma_length)
    data[f"long_ma"] = calculate_ma(data, long_ma_type, long_ma_length)

    balance = 1000
    position = 0  # BTC holdings
    trade_log = []

    for i in range(1, len(data)):
        if pd.notna(data[f"short_ma"].iloc[i]) and pd.notna(data[f"long_ma"].iloc[i]):
            if position == 0 and data[f"short_ma"].iloc[i] > data[f"long_ma"].iloc[i] and data[f"short_ma"].iloc[i - 1] <= data[f"long_ma"].iloc[i - 1]:
                # Buy signal
                position = balance / data["close"].iloc[i]
                trade_log.append({"timestamp": data["timestamp"].iloc[i], "action": "BUY", "price": data["close"].iloc[i], "balance": balance})
                balance = 0

            elif position > 0 and data[f"short_ma"].iloc[i] < data[f"long_ma"].iloc[i] and data[f"short_ma"].iloc[i - 1] >= data[f"long_ma"].iloc[i - 1]:
                # Sell signal
                balance = position * data["close"].iloc[i]
                trade_log.append({"timestamp": data["timestamp"].iloc[i], "action": "SELL", "price": data["close"].iloc[i], "balance": balance})
                position = 0

    # Final balance
    if position > 0:
        balance = position * data["close"].iloc[-1]
        trade_log.append({"timestamp": data["timestamp"].iloc[-1], "action": "SELL", "price": data["close"].iloc[-1], "balance": balance})

    return balance, trade_log

def run_optimization(data):
    """Run optimization for all combinations of moving averages."""
    results = []

    for short_ma_type, long_ma_type in product(["sma", "ema"], repeat=2):
        for short_ma_length, long_ma_length in product(MA_LENGTHS, MA_LENGTHS):
            if short_ma_length >= long_ma_length:
                continue

            print(f"[INFO] Testing {short_ma_type.upper()}({short_ma_length}) vs {long_ma_type.upper()}({long_ma_length})...")
            final_balance, trade_log = backtest_strategy(data.copy(), short_ma_type, short_ma_length, long_ma_type, long_ma_length)

            # Save trade log
            trade_log_df = pd.DataFrame(trade_log)
            trade_log_file = f"{OUTPUT_DIR}trade_log_{short_ma_type}_{short_ma_length}_{long_ma_type}_{long_ma_length}.csv"
            trade_log_df.to_csv(trade_log_file, index=False)

            # Record performance
            results.append({
                "short_ma_type": short_ma_type,
                "short_ma_length": short_ma_length,
                "long_ma_type": long_ma_type,
                "long_ma_length": long_ma_length,
                "final_balance": final_balance
            })

    # Save summary of results
    results_df = pd.DataFrame(results)
    results_df.sort_values(by="final_balance", ascending=False, inplace=True)
    results_file = f"{OUTPUT_DIR}strategy_performance.csv"
    results_df.to_csv(results_file, index=False)
    print("[INFO] Optimization complete. Results saved.")

    # Retain only the best trade log
    if not results_df.empty:
        best_result = results_df.iloc[0]
        best_trade_log_file = f"trade_log_{best_result['short_ma_type']}_{int(best_result['short_ma_length'])}_{best_result['long_ma_type']}_{int(best_result['long_ma_length'])}.csv"
        for file in os.listdir(OUTPUT_DIR):
            if file.startswith("trade_log_") and file != best_trade_log_file:
                os.remove(os.path.join(OUTPUT_DIR, file))
        print(f"[INFO] Retained best trade log: {best_trade_log_file}")

def main():
    """Main function to load data and run optimization."""
    # Load historical data
    data = pd.read_csv(INPUT_CSV, parse_dates=["timestamp"])
    data.sort_values(by="timestamp", inplace=True)

    # Run optimization
    run_optimization(data)

if __name__ == "__main__":
    main()
