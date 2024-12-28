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
# https://www.gnu.org/licenses/.

# Directories for coin data and output
COIN_CSV_DIR = "D:/Historic_prices/hour/"
OUTPUT_DIR = "D:/Process_wallet_data/Backtest/"

import pandas as pd
import os
import random
from itertools import product
from multiprocessing import Pool, cpu_count
import tqdm

# User-configurable parameters
MA_LENGTHS = [5, 10, 15, 20, 30, 40, 50, 60, 70, 80, 90, 100, 240, 960, 1440, 2880]
TAKE_PROFIT_PERCENTAGES = [5, 10, 15, 20, 50, 75, 100, 150]  # Fixed TP percentages
PARTIAL_SELL_PERCENTAGES = [10, 20, 50, 75]  # Percentages to sell at TP
TRADING_FEES_PERCENT = 0.1  # Adjustable trading fees
SLIPPAGE_PERCENT = 0.05  # Adjustable slippage
CPU_CORE_LIMIT = min(20, cpu_count())

def calculate_ma(df, ma_type, length):
    if ma_type == "sma":
        return df["close"].rolling(window=length).mean()
    elif ma_type == "ema":
        return df["close"].ewm(span=length, adjust=False).mean()

def backtest_combination(params):
    """Test a single combination of MAs and TP settings and return results."""
    data, short_ma_type, short_ma_length, long_ma_type, long_ma_length, tp_percent, partial_sell = params
    data = data.copy()

    # Calculate MAs
    data[f"short_ma"] = calculate_ma(data, short_ma_type, short_ma_length)
    data[f"long_ma"] = calculate_ma(data, long_ma_type, long_ma_length)

    # Backtest logic
    balance = 1000
    position = 0  # BTC holdings
    trades = []
    for i in range(max(short_ma_length, long_ma_length), len(data)):
        if pd.notna(data[f"short_ma"].iloc[i]) and pd.notna(data[f"long_ma"].iloc[i]):
            if position == 0 and data[f"short_ma"].iloc[i] > data[f"long_ma"].iloc[i] and data[f"short_ma"].iloc[i - 1] <= data[f"long_ma"].iloc[i - 1]:
                # Buy signal
                entry_price = data["close"].iloc[i] * (1 + SLIPPAGE_PERCENT / 100)
                fee = entry_price * TRADING_FEES_PERCENT / 100
                position = (balance - fee) / entry_price
                balance = 0
                trades.append({"action": "buy", "price": entry_price, "fee": fee, "timestamp": data["timestamp"].iloc[i]})

            elif position > 0:
                # Check for Take Profit
                current_price = data["close"].iloc[i]
                sell_portion = 0
                for percent in PARTIAL_SELL_PERCENTAGES:
                    if current_price >= entry_price * (1 + (tp_percent * percent / 100) / 100):
                        exit_price = current_price * (1 - SLIPPAGE_PERCENT / 100)
                        fee = exit_price * position * (percent / 100) * TRADING_FEES_PERCENT / 100
                        balance += (position * (percent / 100) * exit_price) - fee
                        sell_portion += (percent / 100)
                        trades.append({"action": f"partial_sell_{percent}%", "price": exit_price, "fee": fee, "timestamp": data["timestamp"].iloc[i]})

                # Update remaining position
                position *= (1 - sell_portion)

                # Final sell logic
                if data[f"short_ma"].iloc[i] < data[f"long_ma"].iloc[i] and data[f"short_ma"].iloc[i - 1] >= data[f"long_ma"].iloc[i - 1]:
                    exit_price = current_price * (1 - SLIPPAGE_PERCENT / 100)
                    fee = exit_price * position * TRADING_FEES_PERCENT / 100
                    balance += (position * exit_price) - fee
                    position = 0
                    trades.append({"action": "sell", "price": exit_price, "fee": fee, "timestamp": data["timestamp"].iloc[i]})

    # Final balance
    if position > 0:
        exit_price = data["close"].iloc[-1] * (1 - SLIPPAGE_PERCENT / 100)
        fee = exit_price * position * TRADING_FEES_PERCENT / 100
        balance += (position * exit_price) - fee
        trades.append({"action": "sell (final)", "price": exit_price, "fee": fee, "timestamp": data["timestamp"].iloc[-1]})

    total_pnl = balance - 1000
    max_drawdown = min([trade['price'] for trade in trades if trade['action'] == 'buy'], default=0) - max([trade['price'] for trade in trades if trade['action'].startswith('sell')], default=0)

    return {
        "short_ma": short_ma_type,
        "short_ma_length": short_ma_length,
        "long_ma": long_ma_type,
        "long_ma_length": long_ma_length,
        "tp_percent": tp_percent,
        "partial_sell": partial_sell,
        "final_balance": balance,
        "total_pnl": total_pnl,
        "max_drawdown": max_drawdown,
        "trades": trades,
    }

def run_optimization(data, coin_name):
    """Run optimization using multiprocessing."""
    combinations = []
    for short_ma_type, long_ma_type in product(["sma", "ema"], repeat=2):
        for short_ma_length, long_ma_length in product(MA_LENGTHS, MA_LENGTHS):
            if short_ma_length >= long_ma_length:
                continue
            for tp_percent, partial_sell in product(TAKE_PROFIT_PERCENTAGES, PARTIAL_SELL_PERCENTAGES):
                combinations.append((data, short_ma_type, short_ma_length, long_ma_type, long_ma_length, tp_percent, partial_sell))

    # Use tqdm for a progress bar
    with Pool(CPU_CORE_LIMIT) as pool:
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
        combined_results.groupby(['short_ma', 'short_ma_length', 'long_ma', 'long_ma_length', 'tp_percent', 'partial_sell'])
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

            try:
                # Load data and parse dates
                data = pd.read_csv(os.path.join(COIN_CSV_DIR, file), parse_dates=["Open time"])
                data.rename(columns={"Open time": "timestamp", "Close": "close"}, inplace=True)
                data.sort_values(by="timestamp", inplace=True)

                # Run random iterations for optimization
                run_random_iterations(data, iterations, coin_name)
            except Exception as e:
                print(f"[ERROR] Failed to process {file}: {e}")

    # Aggregate results across all coins
    aggregate_overall_results()

if __name__ == "__main__":
    main()
