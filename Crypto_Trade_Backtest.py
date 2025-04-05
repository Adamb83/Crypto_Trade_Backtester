
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

import pandas as pd
import os
import random
from itertools import product
from multiprocessing import Pool, cpu_count
import tqdm
import numpy as np

# --- Directory Settings ---
COIN_CSV_DIR = "D:/Historic_prices/hour/"
OUTPUT_DIR = "D:/Process_wallet_data/Backtest/"

# --- Candidate Parameters for Optimization ---
# Vary the lengths for the three EMAs and the reentry gap percentage.
# Only combinations where short_ma < mid_ma < long_ma are used.
MA_LENGTHS = [14, 18, 22, 26, 30, 38, 40, 42]
REENTRY_GAP_VALUES = [10, 12, 15]

# --- Fixed Strategy Parameters (from your trading bot) ---
POSITION_SIZE_PERCENT = 7.5        # percent of available balance
SLIPPAGE = 0.0005
FEE_RATE = 0.001
ACCUMULATION_STEPS = 2
PRICE_THRESHOLD = 0.01             # minimal price change in percent
MAX_OPEN_TRADES = 15
CLOSE_PROFIT_BUFFER_PERCENT = 5
MA_TYPE = "ema"                    # using EMA for moving averages

INITIAL_BALANCE = 1000.0           # starting portfolio balance (USDT)
MIN_PERIOD_DAYS = 365              # minimum period of 12 months (in days)
ITERATIONS_PER_COIN = 3            # run 3 iterations per CSV

# --- Utility Function: Calculate Moving Average ---
def calculate_ma(series, window, ma_type):
    if ma_type.lower() == "sma":
        return series.rolling(window=window).mean()
    elif ma_type.lower() == "ema":
        return series.ewm(span=window, adjust=False).mean()
    else:
        raise ValueError("ma_type must be 'sma' or 'ema'")

# --- Simulation Function ---
def simulate_strategy(data, params):
    """
    Simulate the trading strategy over the given DataFrame (data) using a particular combination of settings.
    params: (short_ma_length, mid_ma_length, long_ma_length, reentry_gap)
    """
    short_ma_length, mid_ma_length, long_ma_length, reentry_gap = params

    data = data.copy()
    # Calculate the three EMAs using the 'close' column
    data["short_ma"] = calculate_ma(data["close"], short_ma_length, MA_TYPE)
    data["mid_ma"] = calculate_ma(data["close"], mid_ma_length, MA_TYPE)
    data["long_ma"] = calculate_ma(data["close"], long_ma_length, MA_TYPE)

    balance = INITIAL_BALANCE
    open_positions = []   # list of active positions
    partial_plan = {"active": False, "steps_left": 0, "remaining_value": 0.0}
    trades = []           # record of executed trades (optional)

    # Start simulation from an index where all MAs are available
    start_index = max(short_ma_length, mid_ma_length, long_ma_length)
    
    for i in range(start_index, len(data)):
        current_row = data.iloc[i]
        current_price = current_row["close"]
        timestamp = current_row["timestamp"]
        short_ma_curr = current_row["short_ma"]
        mid_ma_curr = current_row["mid_ma"]
        long_ma_curr = current_row["long_ma"]

        # Calculate price difference from previous candle (in %)
        prev_close = data.iloc[i-1]["close"]
        price_diff = ((current_price - prev_close) / prev_close) * 100

        # --- Step 1: Execute Partial Accumulation if Active ---
        if partial_plan["active"] and partial_plan["steps_left"] > 0:
            step_value = partial_plan["remaining_value"] / partial_plan["steps_left"]
            if step_value > balance:
                step_value = balance
            if step_value > 0:
                actual_buy_price = current_price * (1 + SLIPPAGE)
                fee = step_value * FEE_RATE
                if (step_value + fee) > balance:
                    step_value = balance / (1 + FEE_RATE)
                    fee = step_value * FEE_RATE
                size = step_value / actual_buy_price
                trade = {
                    "timestamp_open": timestamp,
                    "buy_price": current_price,
                    "effective_buy_price": actual_buy_price,
                    "size": size,
                    "buy_fee": fee,
                    "params": params
                }
                open_positions.append(trade)
                trades.append({"action": "buy", "price": current_price, "size": size, "timestamp": timestamp})
                balance -= (step_value + fee)
                partial_plan["remaining_value"] -= step_value
                partial_plan["steps_left"] -= 1
                if partial_plan["steps_left"] == 0:
                    partial_plan["active"] = False

        # --- Step 2: (Removed Take-Profit Check) ---

        # --- Step 3: Crossdown Check ---
        if i > start_index:
            prev_short_ma = data.iloc[i-1]["short_ma"]
            prev_mid_ma = data.iloc[i-1]["mid_ma"]
            if pd.notna(short_ma_curr) and pd.notna(mid_ma_curr) and pd.notna(prev_short_ma) and pd.notna(prev_mid_ma):
                cross_down = (short_ma_curr < mid_ma_curr) and (prev_short_ma >= prev_mid_ma)
                if cross_down:
                    if partial_plan["active"]:
                        partial_plan = {"active": False, "steps_left": 0, "remaining_value": 0.0}
                    for pos in open_positions.copy():
                        profit_percent = ((current_price - pos["buy_price"]) / pos["buy_price"]) * 100
                        if profit_percent > CLOSE_PROFIT_BUFFER_PERCENT:
                            actual_sell_price = current_price * (1 - SLIPPAGE)
                            proceeds = pos["size"] * actual_sell_price
                            fee_sell = proceeds * FEE_RATE
                            balance += (proceeds - fee_sell)
                            trades.append({"action": "sell_crossdown", "price": current_price, "size": pos["size"], "timestamp": timestamp})
                            open_positions.remove(pos)

        # --- Step 4: Entry Condition & Reentry Gap Check ---
        if pd.notna(short_ma_curr) and pd.notna(mid_ma_curr) and pd.notna(long_ma_curr):
            if (short_ma_curr > long_ma_curr) and (mid_ma_curr > long_ma_curr) and (price_diff > PRICE_THRESHOLD) and (len(open_positions) < MAX_OPEN_TRADES):
                can_buy = True
                if open_positions:
                    last_buy_price = open_positions[-1]["buy_price"]
                    needed_price = last_buy_price * (1 - reentry_gap / 100.0)
                    if current_price > needed_price:
                        can_buy = False
                if can_buy and not partial_plan["active"] and balance > 0:
                    trade_value = balance * (POSITION_SIZE_PERCENT / 100.0)
                    partial_plan = {"active": True, "steps_left": ACCUMULATION_STEPS, "remaining_value": trade_value}

    # --- End of Simulation: Liquidate Any Remaining Positions ---
    if open_positions:
        final_price = data.iloc[-1]["close"] * (1 - SLIPPAGE)
        for pos in open_positions:
            proceeds = pos["size"] * final_price
            fee_sell = proceeds * FEE_RATE
            balance += (proceeds - fee_sell)
            trades.append({"action": "sell_final", "price": data.iloc[-1]["close"], "size": pos["size"], "timestamp": data.iloc[-1]["timestamp"]})

    total_pnl = balance - INITIAL_BALANCE
    return {
        "short_ma_length": short_ma_length,
        "mid_ma_length": mid_ma_length,
        "long_ma_length": long_ma_length,
        "reentry_gap": reentry_gap,
        "final_balance": balance,
        "total_pnl": total_pnl,
        "num_trades": len(trades)
    }

# --- Top-Level Helper for Multiprocessing ---
def simulate_strategy_wrapper(args):
    data_sample, params = args
    return simulate_strategy(data_sample, params)

# --- Optimization Over Parameter Grid ---
def run_optimization(data_sample, coin_name):
    combinations = []
    for short in MA_LENGTHS:
        for mid in MA_LENGTHS:
            for long in MA_LENGTHS:
                if not (short < mid < long):
                    continue
                for reentry_gap in REENTRY_GAP_VALUES:
                    combinations.append((short, mid, long, reentry_gap))
    results = []
    cpu_core_limit = min(19, cpu_count())
    args_list = [(data_sample, params) for params in combinations]
    with Pool(cpu_core_limit) as pool:
        for result in tqdm.tqdm(pool.imap_unordered(simulate_strategy_wrapper, args_list),
                                total=len(combinations)):
            result["coin"] = coin_name
            results.append(result)
    return pd.DataFrame(results)

# --- Helper: Get a Random Data Sample with at Least 12 Months ---
def get_random_sample(data):
    n = len(data)
    if n < 2:
        return None
    start_idx = random.randint(0, n - 2)
    start_time = data.iloc[start_idx]["timestamp"]
    min_end_time = start_time + pd.Timedelta(days=MIN_PERIOD_DAYS)
    end_idx = None
    for j in range(start_idx + 1, n):
        if data.iloc[j]["timestamp"] >= min_end_time:
            end_idx = j
            break
    if end_idx is None:
        return None
    end_idx = random.randint(end_idx, n - 1)
    sample = data.iloc[start_idx:end_idx + 1].copy().reset_index(drop=True)
    return sample

# --- Run Random Iterations for a Given Coin ---
def run_random_iterations(data, coin_name):
    aggregated_results = []
    for iteration in range(ITERATIONS_PER_COIN):
        print(f"[INFO] Running iteration {iteration + 1}/{ITERATIONS_PER_COIN} for {coin_name}...")
        sample = get_random_sample(data)
        if sample is None or len(sample) < 100:
            print(f"[WARN] Not enough data for iteration {iteration + 1} for {coin_name}. Skipping.")
            continue
        print(f"[DEBUG] Sample from {sample.iloc[0]['timestamp']} to {sample.iloc[-1]['timestamp']} with {len(sample)} rows.")
        df_results = run_optimization(sample, coin_name)
        aggregated_results.extend(df_results.to_dict(orient="records"))
    if aggregated_results:
        aggregated_df = pd.DataFrame(aggregated_results)
        aggregated_df.sort_values(by="final_balance", ascending=False, inplace=True)
        aggregated_file = os.path.join(OUTPUT_DIR, f"aggregated_{coin_name}_performance.csv")
        aggregated_df.to_csv(aggregated_file, index=False)
        print(f"[INFO] Aggregated results for {coin_name} saved to {aggregated_file}.")
        return aggregated_df
    else:
        print(f"[WARN] No aggregated results for {coin_name}.")
        return pd.DataFrame()

# --- Aggregate Overall Results Across Coins ---
def aggregate_overall_results():
    all_results = []
    for file in os.listdir(OUTPUT_DIR):
        if file.startswith("aggregated_") and file.endswith("_performance.csv"):
            file_path = os.path.join(OUTPUT_DIR, file)
            try:
                df = pd.read_csv(file_path, engine="python")
                all_results.append(df)
            except Exception as e:
                print(f"[ERROR] Failed to read aggregated file {file_path}: {e}")
    if not all_results:
        print("[WARN] No aggregated results found.")
        return
    combined_results = pd.concat(all_results, ignore_index=True)
    grouped_results = combined_results.groupby([
        "short_ma_length", "mid_ma_length", "long_ma_length", "reentry_gap", "coin"
    ]).agg(
        total_final_balance=("final_balance", "sum"),
        average_final_balance=("final_balance", "mean"),
        total_pnl=("total_pnl", "sum"),
        average_pnl=("total_pnl", "mean"),
        num_trials=("final_balance", "count")
    ).reset_index()
    grouped_results.sort_values(by="average_final_balance", ascending=False, inplace=True)
    ranked_file = os.path.join(OUTPUT_DIR, "ranked_settings_performance.csv")
    grouped_results.to_csv(ranked_file, index=False)
    print(f"[INFO] Ranked settings saved to {ranked_file}")
    print("[INFO] Top-performing settings:")
    print(grouped_results.head(10))

# --- Main Function ---
def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    for file in os.listdir(COIN_CSV_DIR):
        if file.endswith(".csv"):
            coin_name = file.replace(".csv", "")
            print(f"[INFO] Processing {file} for coin {coin_name}...")
            try:
                data = pd.read_csv(os.path.join(COIN_CSV_DIR, file))
                # Rename columns if needed
                if "timestamp" not in data.columns:
                    if "Open time" in data.columns:
                        data.rename(columns={"Open time": "timestamp"}, inplace=True)
                    elif "Timestamp" in data.columns:
                        data.rename(columns={"Timestamp": "timestamp"}, inplace=True)
                if "close" not in data.columns:
                    if "Close" in data.columns:
                        data.rename(columns={"Close": "close"}, inplace=True)
                    elif "close_price" in data.columns:
                        data.rename(columns={"close_price": "close"}, inplace=True)
                    else:
                        raise ValueError("CSV missing required column: 'close'")
                # Parse the timestamp column (using dayfirst=True based on your sample format)
                data["timestamp"] = pd.to_datetime(data["timestamp"], dayfirst=True, errors="coerce")
                data.sort_values(by="timestamp", inplace=True)
                run_random_iterations(data, coin_name)
            except Exception as e:
                print(f"[ERROR] Failed to process {file}: {e}")
    aggregate_overall_results()

if __name__ == "__main__":
    main()
