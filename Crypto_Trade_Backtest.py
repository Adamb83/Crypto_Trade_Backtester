# Crypto_Trade_Backtest.py
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
import os
import random
from itertools import product
from multiprocessing import Pool, cpu_count
import tqdm

# Directories for coin data and output
COIN_CSV_DIR = "D:/Historic_prices/"
OUTPUT_DIR = "D:/Process_wallet_data/Backtest/"

# Moving average lengths and RSI settings
MA_LENGTHS = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100, 105, 110, 120, 240]
RSI_LENGTHS = [3, 7, 14]
RSI_THRESHOLDS = range(10, 50, 5)

# CPU core limit
CPU_LIMIT = min(20, cpu_count())

def calculate_ma(df, ma_type, length):
    if ma_type == "sma":
        return df["close"].rolling(window=length).mean()
    elif ma_type == "ema":
        return df["close"].ewm(span=length, adjust=False).mean()

def calculate_rsi(df, length):
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(window=length).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=length).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def backtest_combination(params):
    """Test a single combination of MAs and RSI and return results."""
    data, short_ma_type, short_ma_length, long_ma_type, long_ma_length, rsi_length, rsi_threshold = params
    data = data.copy()

    # Calculate MAs and RSI
    data[f"short_ma"] = calculate_ma(data, short_ma_type, short_ma_length)
    data[f"long_ma"] = calculate_ma(data, long_ma_type, long_ma_length)
    if rsi_length:
        data[f"rsi_{rsi_length}"] = calculate_rsi(data, rsi_length)

    # Backtest logic
    balance = 1000
    position = 0  # BTC holdings
    for i in range(1, len(data)):
        if pd.notna(data[f"short_ma"].iloc[i]) and pd.notna(data[f"long_ma"].iloc[i]):
            if position == 0 and data[f"short_ma"].iloc[i] > data[f"long_ma"].iloc[i] and data[f"short_ma"].iloc[i - 1] <= data[f"long_ma"].iloc[i - 1]:
                if rsi_length and data[f"rsi_{rsi_length}"].iloc[i] <= rsi_threshold:
                    continue
                position = balance / data["close"].iloc[i]
                balance = 0
            elif position > 0 and data[f"short_ma"].iloc[i] < data[f"long_ma"].iloc[i] and data[f"short_ma"].iloc[i - 1] >= data[f"long_ma"].iloc[i - 1]:
                balance = position * data["close"].iloc[i]
                position = 0

    # Final balance
    if position > 0:
        balance = position * data["close"].iloc[-1]

    return {
        "short_ma": short_ma_type,
        "short_ma_length": short_ma_length,
        "long_ma": long_ma_type,
        "long_ma_length": long_ma_length,
        "rsi_length": rsi_length,
        "rsi_threshold": rsi_threshold,
        "final_balance": balance,
    }

def run_optimization(data, coin_name):
    """Run optimization using multiprocessing."""
    combinations = []
    for short_ma_type, long_ma_type in product(["sma", "ema"], repeat=2):
        for short_ma_length, long_ma_length in product(MA_LENGTHS, MA_LENGTHS):
            if short_ma_length >= long_ma_length:
                continue
            for rsi_length, rsi_threshold in product(RSI_LENGTHS, RSI_THRESHOLDS):
                combinations.append((data, short_ma_type, short_ma_length, long_ma_type, long_ma_length, rsi_length, rsi_threshold))

    # Use tqdm for a progress bar
    with Pool(CPU_LIMIT) as pool:
        results = []
        for result in tqdm.tqdm(pool.imap_unordered(backtest_combination, combinations), total=len(combinations)):
            result["coin"] = coin_name
            results.append(result)

    # Convert results to DataFrame
    return pd.DataFrame(results)

def run_random_iterations(data, iterations, coin_name):
    """Run the optimization over random time periods and aggregate results."""
    aggregated_results = []
    for iteration in range(iterations):
        print(f"[INFO] Running iteration {iteration + 1}/{iterations} for {coin_name}...")

        # Randomly sample start and end dates
        start_index = random.randint(0, len(data) // 2)
        end_index = random.randint(start_index + 1, len(data) - 1)

        sampled_data = data.iloc[start_index:end_index]

        print(f"[DEBUG] Start index: {start_index}, End index: {end_index}")

        # Optimize on the sampled data
        results = run_optimization(sampled_data, coin_name)
        aggregated_results.extend(results.to_dict(orient="records"))

    # Aggregate all results into a single DataFrame
    aggregated_df = pd.DataFrame(aggregated_results)
    aggregated_df.sort_values(by="final_balance", ascending=False, inplace=True)
    aggregated_file = f"{OUTPUT_DIR}aggregated_{coin_name}_performance.csv"
    aggregated_df.to_csv(aggregated_file, index=False)
    print(f"[INFO] Aggregated results for {coin_name} saved.")
    return aggregated_df

def aggregate_overall_results():
    """Aggregate results across all coins and rank settings."""
    all_results = []
    for file in os.listdir(OUTPUT_DIR):
        if file.startswith("aggregated_") and file.endswith("_performance.csv"):
            file_path = os.path.join(OUTPUT_DIR, file)
            df = pd.read_csv(file_path)
            all_results.append(df)

    combined_results = pd.concat(all_results, ignore_index=True)

    # Group by settings and sum final balances
    grouped_results = (
        combined_results.groupby(['short_ma', 'short_ma_length', 'long_ma', 'long_ma_length', 'rsi_length', 'rsi_threshold'])
        .agg(total_final_balance=('final_balance', 'sum'))
        .reset_index()
    )

    # Sort by total final balance
    grouped_results.sort_values(by='total_final_balance', ascending=False, inplace=True)

    # Save the ranked list to a CSV
    ranked_file = os.path.join(OUTPUT_DIR, "ranked_settings_performance.csv")
    grouped_results.to_csv(ranked_file, index=False)
    print(f"[INFO] Ranked settings saved to {ranked_file}")

    print("[INFO] Top-performing settings:")
    print(grouped_results.head(10))

def main():
    """Main function to load data and run optimization."""
    iterations = int(input("Enter the number of random sampling iterations per coin: "))

    for file in os.listdir(COIN_CSV_DIR):
        if file.endswith(".csv"):
            coin_name = file.replace(".csv", "")
            print(f"[INFO] Processing {file}...")
            data = pd.read_csv(os.path.join(COIN_CSV_DIR, file), parse_dates=["timestamp"])
            data.sort_values(by="timestamp", inplace=True)

            run_random_iterations(data, iterations, coin_name)

    aggregate_overall_results()

if __name__ == "__main__":
    main()
#Working