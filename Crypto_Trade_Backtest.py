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
OUTPUT_DIR   = "D:/Historic_prices/hour/"

# --- Candidate Parameters for Optimization ---
MA_LENGTHS         = [14, 18, 22, 26, 30, 38, 40, 42, 50, 100, 150, 200]
REENTRY_GAP_VALUES = [7, 10, 12, 15, 20]

# --- Fixed Strategy Parameters ---
POSITION_SIZE_PERCENT       = 7.5
SLIPPAGE                    = 0.0005
FEE_RATE                    = 0.001
ACCUMULATION_STEPS          = 2
PRICE_THRESHOLD             = 0.01
MAX_OPEN_TRADES             = 15
CLOSE_PROFIT_BUFFER_PERCENT = 5
MA_TYPE                     = "ema"

INITIAL_BALANCE    = 1000.0
MIN_PERIOD_DAYS    = 365
ITERATIONS_PER_COIN = 10

# --- Utility Function: Calculate Moving Average ---
def calculate_ma(series, window, ma_type):
    if ma_type.lower() == "sma":
        return series.rolling(window=window).mean()
    elif ma_type.lower() == "ema":
        return series.ewm(span=window, adjust=False).mean()
    else:
        raise ValueError("ma_type must be 'sma' or 'ema'")

# --- Strategy Simulation ---
def simulate_strategy(data, params):
    short_ma_length, mid_ma_length, long_ma_length, reentry_gap = params
    data = data.copy()
    data["short_ma"] = calculate_ma(data["close"], short_ma_length, MA_TYPE)
    data["mid_ma"]   = calculate_ma(data["close"], mid_ma_length, MA_TYPE)
    data["long_ma"]  = calculate_ma(data["close"], long_ma_length, MA_TYPE)

    balance, open_positions = INITIAL_BALANCE, []
    partial_plan = {"active": False, "steps_left": 0, "remaining_value": 0.0}
    trades = []
    start_index = max(short_ma_length, mid_ma_length, long_ma_length)

    for i in range(start_index, len(data)):
        row = data.iloc[i]
        prev_row = data.iloc[i-1]
        price, prev_price = row["close"], prev_row["close"]
        price_diff = (price - prev_price) / prev_price * 100

        # Partial accumulation
        if partial_plan["active"] and partial_plan["steps_left"] > 0:
            value = min(partial_plan["remaining_value"] / partial_plan["steps_left"], balance)
            if value > 0:
                buy_price = price * (1 + SLIPPAGE)
                fee = value * FEE_RATE
                size = value / buy_price
                open_positions.append({"price": price, "size": size})
                trades.append({"action": "buy", "price": price, "size": size})
                balance -= (value + fee)
                partial_plan["remaining_value"] -= value
                partial_plan["steps_left"] -= 1
                if partial_plan["steps_left"] == 0:
                    partial_plan["active"] = False

        # Crossdown exit
        if pd.notna(row["short_ma"]) and pd.notna(row["mid_ma"]):
            if row["short_ma"] < row["mid_ma"] and prev_row["short_ma"] >= prev_row["mid_ma"]:
                partial_plan = {"active": False, "steps_left": 0, "remaining_value": 0.0}
                for pos in open_positions.copy():
                    profit_pct = (price - pos["price"]) / pos["price"] * 100
                    if profit_pct > CLOSE_PROFIT_BUFFER_PERCENT:
                        sell_price = price * (1 - SLIPPAGE)
                        proceeds = pos["size"] * sell_price
                        fee = proceeds * FEE_RATE
                        balance += (proceeds - fee)
                        trades.append({"action": "sell_crossdown", "price": price, "size": pos["size"]})
                        open_positions.remove(pos)

        # Entry condition: strict cross-up (short > mid > long)
        if pd.notna(row["short_ma"]) and pd.notna(row["mid_ma"]) and pd.notna(row["long_ma"]):
            if (row["short_ma"] > row["mid_ma"] > row["long_ma"]
                and price_diff > PRICE_THRESHOLD
                and len(open_positions) < MAX_OPEN_TRADES):
                can_buy = True
                # prevent reentry too soon
                if open_positions and price > open_positions[-1]["price"] * (1 - reentry_gap/100):
                    can_buy = False
                if can_buy and not partial_plan["active"] and balance > 0:
                    partial_plan = {"active": True,
                                    "steps_left": ACCUMULATION_STEPS,
                                    "remaining_value": balance * (POSITION_SIZE_PERCENT/100)}

    # Liquidate at final bar
    if open_positions:
        final_price = data.iloc[-1]["close"] * (1 - SLIPPAGE)
        for pos in open_positions:
            proceeds = pos["size"] * final_price
            fee = proceeds * FEE_RATE
            balance += (proceeds - fee)
            trades.append({"action": "sell_final", "price": final_price, "size": pos["size"]})

    return {"short_ma_length": short_ma_length, "mid_ma_length": mid_ma_length,
            "long_ma_length": long_ma_length, "reentry_gap": reentry_gap,
            "final_balance": balance,
            "total_pnl": balance - INITIAL_BALANCE,
            "num_trades": len(trades)}

# --- Multiprocessing Wrapper ---
def simulate_strategy_wrapper(args):
    return simulate_strategy(*args)

# --- Random Sample Fetcher ---
def get_random_sample(data):
    n = len(data)
    if n < 2: return None
    si = random.randint(0, n-2)
    st = data.iloc[si]["timestamp"]
    min_end = st + pd.Timedelta(days=MIN_PERIOD_DAYS)
    candidates = [j for j in range(si+1, n) if data.iloc[j]["timestamp"] >= min_end]
    ei = random.randint(candidates[0], n-1) if candidates else random.randint(si+1, n-1)
    return data.iloc[si:ei+1].copy().reset_index(drop=True)

# --- Per‑Coin Iterations & Ranking ---
def run_random_iterations(data, coin_name):
    records = []
    for i in range(ITERATIONS_PER_COIN):
        print(f"[INFO] Iter {i+1}/{ITERATIONS_PER_COIN} for {coin_name}")
        sample = get_random_sample(data)
        if sample is None or len(sample) < 100:
            print(f"[WARN] Skipping iter {i+1}, only {len(sample) if sample is not None else 0} rows")
            continue
        combos = [(sample, p) for p in product(MA_LENGTHS, MA_LENGTHS, MA_LENGTHS, REENTRY_GAP_VALUES) if p[0]<p[1]<p[2]]
        with Pool(min(cpu_count(), 19)) as pool:
            for r in tqdm.tqdm(pool.imap_unordered(simulate_strategy_wrapper, combos), total=len(combos)):
                r['coin'] = coin_name
                records.append(r)

    if not records:
        print(f"[WARN] No results for {coin_name}")
        return pd.DataFrame()
    df = pd.DataFrame(records)
    df['pct_gain'] = df['total_pnl']/INITIAL_BALANCE*100
    pf = lambda g: g.loc[g['total_pnl']>0,'total_pnl'].sum() / -g.loc[g['total_pnl']<0,'total_pnl'].sum() if any(g['total_pnl']<0) else np.nan
    summary = df.groupby(['short_ma_length','mid_ma_length','long_ma_length','reentry_gap']).apply(
        lambda g: pd.Series({
            'avg_pct_gain': g['pct_gain'].mean(),
            'std_pct_gain': g['pct_gain'].std(),
            'runs': len(g),
            'avg_profit_factor': pf(g)
        })
    ).reset_index()
    top_gain = summary.sort_values('avg_pct_gain',ascending=False)
    top_pf   = summary.sort_values('avg_profit_factor',ascending=False)
    print(f"\n--- {coin_name} Top by Gain ---")
    print(top_gain.head(10).to_string(index=False))
    print(f"\n--- {coin_name} Top by PF ---")
    print(top_pf.head(10).to_string(index=False))
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    summary.to_csv(os.path.join(OUTPUT_DIR,f"parameter_summary_{coin_name}.csv"),index=False)
    pd.DataFrame(records).to_csv(os.path.join(OUTPUT_DIR,f"aggregated_{coin_name}_performance.csv"),index=False)
    return df

# --- Overall Aggregation & Ranking ---
def aggregate_overall_results():
    files = [f for f in os.listdir(OUTPUT_DIR) if f.startswith('aggregated_') and f.endswith('_performance.csv')]
    if not files:
        print("[WARN] No aggregated files.")
        return
    df_list = []
    for f in files:
        try:
            df_list.append(pd.read_csv(os.path.join(OUTPUT_DIR,f)))
        except:
            pass
    combined = pd.concat(df_list,ignore_index=True)
    combined['pct_gain'] = combined['total_pnl']/INITIAL_BALANCE*100
    pf_all = lambda g: g.loc[g['total_pnl']>0,'total_pnl'].sum() / -g.loc[g['total_pnl']<0,'total_pnl'].sum() if any(g['total_pnl']<0) else np.nan
    overall = combined.groupby(['short_ma_length','mid_ma_length','long_ma_length','reentry_gap']).agg(
        avg_pct_gain=('pct_gain','mean'),
        std_pct_gain=('pct_gain','std'),
        runs=('pct_gain','count'),
        avg_profit_factor=('total_pnl', lambda x: pf_all(combined.loc[x.index]))
    ).reset_index()
    print("\n=== Overall Top by Gain ===")
    print(overall.sort_values('avg_pct_gain',ascending=False).head(10).to_string(index=False))
    print("\n=== Overall Top by PF ===")
    print(overall.sort_values('avg_profit_factor',ascending=False).head(10).to_string(index=False))
    overall.to_csv(os.path.join(OUTPUT_DIR,'overall_parameter_ranking.csv'),index=False)

# --- Main Execution: only raw data files ---
def main():
    os.makedirs(OUTPUT_DIR,exist_ok=True)
    for file in os.listdir(COIN_CSV_DIR):
        if not file.endswith('.csv'): continue
        if file.startswith(('aggregated_','parameter_summary_','overall_parameter_ranking')): continue
        coin = file.rsplit('.',1)[0]
        print(f"[INFO] Processing {coin}...")
        try:
            df = pd.read_csv(os.path.join(COIN_CSV_DIR,file))
            if 'timestamp' not in df.columns:
                df.rename(columns={'Open time':'timestamp','Timestamp':'timestamp'},inplace=True)
            if 'close' not in df.columns:
                df.rename(columns={'Close':'close','close_price':'close'},inplace=True)
            df['timestamp'] = pd.to_datetime(df['timestamp'],dayfirst=True,errors='coerce')
            df.sort_values('timestamp',inplace=True)
            run_random_iterations(df,coin)
        except Exception as e:
            print(f"[ERROR] {coin}: {e}")
    aggregate_overall_results()

if __name__=='__main__':
    main()
