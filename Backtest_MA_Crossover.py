import os
import pandas as pd
from datetime import datetime

########################
# USER-DEFINED SETTINGS
########################
SINGLE_ASSET_FOLDER = "D:/Historic_prices/hour/"
CSV_TIMESTAMP_COL   = "Open time"  # Column to parse as datetime
CSV_CLOSE_COL       = "Close"      # Column for close price

SHORT_MA_LENGTH       = 18         # short MA length
MID_MA_LENGTH         = 27         # mid MA length
LONG_MA_LENGTH        = 41         # long MA length

SHORT_MA_TYPE         = "ema"
MID_MA_TYPE           = "ema"
LONG_MA_TYPE          = "ema"
PRICE_THRESHOLD       = 0.01

INITIAL_BALANCE       = 1000
POSITION_SIZE_PERCENT = 15
TAKE_PROFIT_PERCENT   = 9000
REENTRY_GAP_PERCENT   = 12
SLIPPAGE              = 0.0005
FEE_RATE              = 0.00
CLOSE_PROFIT_BUFFER_PERCENT = 5
CLOSE_ALL_ON_CROSSDOWN      = False
MAX_OPEN_TRADES             = 15
ACCUMULATION_STEPS    = 2
CLOSE_PROFIT_ON_CROSSDOWN = True
INCREASE_X_PERCENT    = 0  # martingale increment percent

########################
# UTILITY FUNCTIONS
########################
def is_valid_price_history_file(filepath: str) -> bool:
    try:
        sample_df = pd.read_csv(filepath, nrows=1, low_memory=False)
        cols = sample_df.columns
        return CSV_TIMESTAMP_COL in cols and CSV_CLOSE_COL in cols
    except:
        return False


def calculate_ma(prices: pd.Series, window: int, ma_type: str) -> pd.Series:
    mt = ma_type.lower()
    if mt == "sma":
        return prices.rolling(window=window).mean()
    elif mt == "ema":
        return prices.ewm(span=window, adjust=False).mean()
    else:
        raise ValueError("ma_type must be 'sma' or 'ema'.")


def compute_equity(balance: float, open_positions: list, current_price: float) -> float:
    return balance + sum(pos["size"] * current_price for pos in open_positions)


def calculate_max_drawdown(equity_curve: list) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for eq in equity_curve:
        peak = max(peak, eq)
        dd = (peak - eq) / peak
        max_dd = max(max_dd, dd)
    return max_dd * 100

########################
# BACKTEST FUNCTION
########################

def backtest_partial_accumulation_with_dd_and_partial_sells(df: pd.DataFrame):
    # Buy & Hold baseline
    first_price = df["close"].iloc[0]
    buy_and_hold_size = INITIAL_BALANCE / first_price
    buy_and_hold_curve = []

    # Compute MAs
    df["short_ma"] = calculate_ma(df["close"], SHORT_MA_LENGTH, SHORT_MA_TYPE)
    df["mid_ma"]   = calculate_ma(df["close"], MID_MA_LENGTH, MID_MA_TYPE)
    df["long_ma"]  = calculate_ma(df["close"], LONG_MA_LENGTH, LONG_MA_TYPE)

    balance = INITIAL_BALANCE
    open_positions = []
    closed_trades = []
    equity_curve = []
    max_open_positions = 0
    partial_plan = {"active": False, "steps_left": 0, "remaining_value": 0.0}
    last_buy_price = None
    next_trade_value = None
    peak_equity = INITIAL_BALANCE

    def do_buy_trade(trade_value, price, timestamp):
        nonlocal balance, last_buy_price
        if trade_value <= 0 or balance <= 0:
            return
        trade_value = min(trade_value, balance)
        buy_price = price * (1 + SLIPPAGE)
        fee = trade_value * FEE_RATE
        size = trade_value / buy_price
        balance -= (trade_value + fee)
        open_positions.append({
            "timestamp_open": timestamp,
            "buy_price": price,
            "effective_buy_price": buy_price,
            "size": size,
            "buy_fee": fee
        })
        last_buy_price = price

    def do_partial_sell(pos, ratio, price, timestamp):
        nonlocal balance
        sell_price = price * (1 - SLIPPAGE)
        sell_size = pos["size"] * ratio
        proceeds = sell_size * sell_price
        fee = proceeds * FEE_RATE
        balance += (proceeds - fee)
        buy_cost = sell_size * pos["effective_buy_price"]
        closed_trades.append({
            "timestamp_open": pos["timestamp_open"],
            "timestamp_close": timestamp,
            "buy_price": pos["buy_price"],
            "sell_price": price,
            "size": sell_size,
            "gross_pnl": proceeds - buy_cost,
            "net_pnl": (proceeds - fee) - buy_cost
        })
        pos["size"] -= sell_size
        if pos["size"] < 1e-8:
            open_positions.remove(pos)

    # Loop candles
    for i in range(len(df)):
        price = df["close"].iloc[i]
        ts = df["timestamp"].iloc[i]

        # Buy & hold
        buy_and_hold_curve.append(buy_and_hold_size * price)

        # Compute equity
        equity = compute_equity(balance, open_positions, price)
        equity_curve.append(equity)
        peak_equity = max(peak_equity, equity)

        # Execute partial plan
        if partial_plan["active"] and partial_plan["steps_left"] > 0:
            step = partial_plan["remaining_value"] / partial_plan["steps_left"]
            do_buy_trade(step, price, ts)
            partial_plan["remaining_value"] -= step
            partial_plan["steps_left"] -= 1
            if partial_plan["steps_left"] == 0:
                partial_plan["active"] = False
                if next_trade_value is None:
                    next_trade_value = step
                else:
                    next_trade_value *= (1 + INCREASE_X_PERCENT/100)

        # Take-profit
        target = 1 + (TAKE_PROFIT_PERCENT / 100)
        for pos in open_positions[:]:
            if price >= pos["buy_price"] * target:
                do_partial_sell(pos, 1.0, price, ts)

        # Skip until MAs ready
        if i < max(SHORT_MA_LENGTH, MID_MA_LENGTH, LONG_MA_LENGTH):
            continue

        short_ma = df["short_ma"].iloc[i]
        mid_ma   = df["mid_ma"].iloc[i]
        long_ma  = df["long_ma"].iloc[i]
        prev_short = df["short_ma"].iloc[i-1]
        prev_mid   = df["mid_ma"].iloc[i-1]
        prev_close = df["close"].iloc[i-1]
        price_diff = (price - prev_close) / prev_close * 100

        # Crossdown exit
        cross_down = (short_ma < mid_ma) and (prev_short >= prev_mid)
        if cross_down:
            partial_plan = {"active": False, "steps_left": 0, "remaining_value": 0.0}
            if CLOSE_ALL_ON_CROSSDOWN:
                for pos in open_positions[:]:
                    do_partial_sell(pos, 1.0, price, ts)
            elif CLOSE_PROFIT_ON_CROSSDOWN:
                for pos in open_positions[:]:
                    pnl_pct = (price - pos["buy_price"]) / pos["buy_price"] * 100
                    if pnl_pct > CLOSE_PROFIT_BUFFER_PERCENT:
                        do_partial_sell(pos, 1.0, price, ts)

        # Entry: strict cross-up (short > mid > long)
        if pd.notna(short_ma) and pd.notna(mid_ma) and pd.notna(long_ma):
            if (short_ma > mid_ma > long_ma
                and not partial_plan["active"]
                and price_diff > PRICE_THRESHOLD):
                if len(open_positions) < MAX_OPEN_TRADES:
                    can_buy = True
                    if open_positions and last_buy_price is not None:
                        needed = last_buy_price * (1 - REENTRY_GAP_PERCENT/100)
                        if price > needed:
                            can_buy = False
                    if can_buy:
                        eq_now = compute_equity(balance, open_positions, price)
                        base_val = eq_now * (POSITION_SIZE_PERCENT/100)
                        if next_trade_value is None or not open_positions:
                            next_trade_value = base_val
                        else:
                            next_trade_value *= (1 + INCREASE_X_PERCENT/100)
                        trade_val = min(next_trade_value, balance)
                        if trade_val > 0:
                            partial_plan = {
                                "active": True,
                                "steps_left": ACCUMULATION_STEPS,
                                "remaining_value": trade_val
                            }

        max_open_positions = max(max_open_positions, len(open_positions))

    # Final liquidation
    final_price = df["close"].iloc[-1]
    final_equity = compute_equity(balance, open_positions, final_price)
    equity_curve.append(final_equity)

    results = {
        "final_balance": balance,
        "final_equity": final_equity,
        "total_pnl": final_equity - INITIAL_BALANCE,
        "max_drawdown": calculate_max_drawdown(equity_curve),
        "open_positions": open_positions,
        "closed_trades": closed_trades,
        "equity_curve": equity_curve,
        "max_open_positions": max_open_positions,
        "buy_and_hold_curve": buy_and_hold_curve
    }
    return results

########################
# MAIN SCRIPT
########################
def main():
    files = [f for f in os.listdir(SINGLE_ASSET_FOLDER) if f.endswith(".csv")]
    if not files:
        print(f"[ERROR] No CSV in {SINGLE_ASSET_FOLDER}")
        return
    valid = next((f for f in files if is_valid_price_history_file(os.path.join(SINGLE_ASSET_FOLDER, f))), None)
    if not valid:
        print("[ERROR] No valid CSV found.")
        return
    path = os.path.join(SINGLE_ASSET_FOLDER, valid)
    print(f"[INFO] Using {path}")

    df = pd.read_csv(
        path,
        parse_dates=[CSV_TIMESTAMP_COL],
        dayfirst=True,
        low_memory=False
    )
    df.rename(columns={CSV_TIMESTAMP_COL: "timestamp", CSV_CLOSE_COL: "close"}, inplace=True)
    df.dropna(subset=["timestamp"], inplace=True)
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)

    seg = len(df) // 3
    for idx, segment in enumerate((df.iloc[:seg], df.iloc[seg:2*seg], df.iloc[2*seg:]), 1):
        print(f"[INFO] Segment {idx}...")
        res = backtest_partial_accumulation_with_dd_and_partial_sells(segment)
        print(f"Segment {idx} - Balance: {res['final_balance']:.2f}, PnL: {res['total_pnl']:.2f}, Max DD: {res['max_drawdown']:.2f}%")

if __name__ == '__main__':
    main()
