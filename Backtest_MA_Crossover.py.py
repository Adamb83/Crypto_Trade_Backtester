import os
import pandas as pd
from datetime import datetime

########################
# USER-DEFINED SETTINGS
########################
SINGLE_ASSET_FOLDER = "D:/Historic_prices/hour/"
CSV_TIMESTAMP_COL   = "Open time"  # Column to parse as datetime
CSV_CLOSE_COL       = "Close"      # Column for close price


SHORT_MA_LENGTH       = 18  
MID_MA_LENGTH         = 27  
LONG_MA_LENGTH        = 40  

SHORT_MA_TYPE         = "ema"
MID_MA_TYPE           = "ema" 
LONG_MA_TYPE          = "ema"
PRICE_THRESHOLD = 0.01


INITIAL_BALANCE       = 1000
POSITION_SIZE_PERCENT = 15
TAKE_PROFIT_PERCENT   = 9000    
REENTRY_GAP_PERCENT   = 12  
SLIPPAGE              = 0.0005  
FEE_RATE              = 0.00   
CLOSE_PROFIT_BUFFER_PERCENT = 5
CLOSE_ALL_ON_CROSSDOWN = False  
MAX_OPEN_TRADES = 15
ACCUMULATION_STEPS    = 2       
CLOSE_PROFIT_ON_CROSSDOWN = True

# New parameter for Martingale increase
INCREASE_X_PERCENT = 0 # Increase each subsequent order by 10% (user-defined)

########################
# UTILITY FUNCTIONS
########################
def is_valid_price_history_file(filepath: str) -> bool:
    try:
        sample_df = pd.read_csv(filepath, nrows=1, low_memory=False)
        columns = sample_df.columns
        return "Open time" in columns and "Close" in columns
    except Exception:
        return False

def calculate_ma(prices: pd.Series, window: int, ma_type: str) -> pd.Series:
    ma_type = ma_type.lower()
    if ma_type == "sma":
        return prices.rolling(window=window).mean()
    elif ma_type == "ema":
        return prices.ewm(span=window, adjust=False).mean()
    else:
        raise ValueError("ma_type must be 'sma' or 'ema'.")

def compute_equity(balance: float, open_positions: list, current_price: float) -> float:
    pos_value = sum(pos["size"] * current_price for pos in open_positions)
    return balance + pos_value

def calculate_max_drawdown(equity_curve: list) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak
        if dd > max_dd:
            max_dd = dd
    return max_dd * 100.0

########################
# BACKTEST FUNCTION
########################
def backtest_partial_accumulation_with_dd_and_partial_sells(df: pd.DataFrame):
    from datetime import datetime

    # 1) Buy & Hold Baseline
    first_price = df["close"].iloc[0]
    buy_and_hold_size = INITIAL_BALANCE / first_price
    buy_and_hold_curve = []

    # 2) Strategy Setup
    df["short_ma"] = calculate_ma(df["close"], SHORT_MA_LENGTH, SHORT_MA_TYPE)
    df["mid_ma"]   = calculate_ma(df["close"], MID_MA_LENGTH, MID_MA_TYPE)
    df["long_ma"]  = calculate_ma(df["close"], LONG_MA_LENGTH, LONG_MA_TYPE)

    balance         = INITIAL_BALANCE
    open_positions  = []
    closed_trades   = []
    equity_curve    = []
    max_open_positions = 0

    partial_plan = {
        "active": False,
        "steps_left": 0,
        "remaining_value": 0.0
    }

    last_buy_price = None  
    peak_equity = INITIAL_BALANCE

    # Initialize next_trade_value as None
    next_trade_value = None

    def do_buy_trade(trade_value: float, current_price: float, timestamp: datetime) -> None:
        nonlocal balance, open_positions, last_buy_price
        if trade_value <= 0 or balance <= 0:
            return
        trade_value = min(trade_value, balance)

        actual_buy_price = current_price * (1 + SLIPPAGE)
        cost_before_fee  = trade_value
        buy_fee          = cost_before_fee * FEE_RATE
        total_cost       = cost_before_fee + buy_fee

        if total_cost > balance:
            cost_before_fee = balance / (1 + FEE_RATE)
            buy_fee         = cost_before_fee * FEE_RATE
            total_cost      = cost_before_fee + buy_fee

        size = cost_before_fee / actual_buy_price
        balance -= total_cost

        open_positions.append({
            "timestamp_open": timestamp,
            "buy_price": current_price,
            "effective_buy_price": actual_buy_price,
            "size": size,
            "buy_fee": buy_fee
        })

        last_buy_price = current_price

    def do_partial_sell(position: dict, sell_ratio: float, current_price: float, timestamp: datetime):
        nonlocal balance, closed_trades, open_positions

        actual_sell_price   = current_price * (1 - SLIPPAGE)
        sell_size           = position["size"] * sell_ratio
        proceeds_before_fee = sell_size * actual_sell_price
        sell_fee            = proceeds_before_fee * FEE_RATE
        net_proceeds        = proceeds_before_fee - sell_fee

        balance += net_proceeds

        buy_cost_for_this_sell = sell_size * position["effective_buy_price"]
        gross_pnl = proceeds_before_fee - buy_cost_for_this_sell
        net_pnl   = net_proceeds - buy_cost_for_this_sell

        holding_sec  = (timestamp - position["timestamp_open"]).total_seconds()
        holding_days = holding_sec / (3600 * 24)

        closed_trade = {
            "timestamp_open": position["timestamp_open"],
            "timestamp_close": timestamp,
            "buy_price": position["buy_price"],
            "effective_buy_price": position["effective_buy_price"],
            "sell_price": current_price,
            "effective_sell_price": actual_sell_price,
            "size": sell_size,
            "buy_fee": position["buy_fee"],
            "sell_fee": sell_fee,
            "gross_pnl": gross_pnl,
            "net_pnl": net_pnl,
            "holding_days": holding_days
        }
        closed_trades.append(closed_trade)

        position["size"] -= sell_size
        if position["size"] < 1e-8:
            position["size"] = 0.0

    ### Main candle loop
    for i in range(len(df)):
        current_price = df["close"].iloc[i]
        timestamp     = df["timestamp"].iloc[i]

        # 1) Buy & hold equity
        buy_and_hold_equity = buy_and_hold_size * current_price
        buy_and_hold_curve.append(buy_and_hold_equity)

        # 2) Current equity
        current_equity = compute_equity(balance, open_positions, current_price)
        equity_curve.append(current_equity)
        if current_equity > peak_equity:
            peak_equity = current_equity

        # 3) Partial accumulation plan execution
        if partial_plan["active"] and partial_plan["steps_left"] > 0:
            step_value = partial_plan["remaining_value"] / partial_plan["steps_left"]
            do_buy_trade(step_value, current_price, timestamp)
            partial_plan["remaining_value"] -= step_value
            partial_plan["steps_left"]      -= 1
            if partial_plan["steps_left"] == 0:
                partial_plan["active"] = False

                # After completing an accumulation cycle, update next_trade_value for future trades
                if next_trade_value is None:
                    next_trade_value = partial_plan["remaining_value"] + step_value
                else:
                    next_trade_value *= (1 + INCREASE_X_PERCENT/100.0)

        # 4) Check take-profit for open positions
        target_mult = 1 + (TAKE_PROFIT_PERCENT / 100.0)
        for pos in open_positions[:]:
            target_price = pos["buy_price"] * target_mult
            if current_price >= target_price:
                do_partial_sell(pos, 1.0, current_price, timestamp)
                if pos["size"] < 1e-8:
                    open_positions.remove(pos)

        # 5) Skip if not enough data or if MAs are NaN
        if i < max(SHORT_MA_LENGTH, MID_MA_LENGTH, LONG_MA_LENGTH):
            continue
        if pd.isna(df["short_ma"].iloc[i]) or pd.isna(df["mid_ma"].iloc[i]) or pd.isna(df["long_ma"].iloc[i]):
            continue

        short_ma_curr = df["short_ma"].iloc[i]
        mid_ma_curr   = df["mid_ma"].iloc[i]
        long_ma_curr  = df["long_ma"].iloc[i]
        price_diff = ((current_price - df["close"].iloc[i - 1]) / df["close"].iloc[i - 1]) * 100

        # 6) Check for closing condition: shortest MA crosses below middle MA
        short_ma_prev = df["short_ma"].iloc[i - 1]
        mid_ma_prev   = df["mid_ma"].iloc[i - 1]
        cross_down = (short_ma_curr < mid_ma_curr) and (short_ma_prev >= mid_ma_prev)
        if cross_down:
            if partial_plan["active"]:
                partial_plan["active"] = False
                partial_plan["steps_left"] = 0
                partial_plan["remaining_value"] = 0.0

            if CLOSE_ALL_ON_CROSSDOWN:
                for pos in open_positions[:]:
                    do_partial_sell(pos, 1.0, current_price, timestamp)
                    if pos["size"] < 1e-8:
                        open_positions.remove(pos)
            else:
                if CLOSE_PROFIT_ON_CROSSDOWN:
                    for pos in open_positions[:]:
                        profit_percent = ((current_price - pos["buy_price"]) / pos["buy_price"]) * 100
                        if profit_percent > CLOSE_PROFIT_BUFFER_PERCENT:
                            do_partial_sell(pos, 1.0, current_price, timestamp)
                            if pos["size"] < 1e-8:
                                open_positions.remove(pos)

        # 7) Entry condition with simplified reentry gap check
        if (short_ma_curr > long_ma_curr) and (mid_ma_curr > long_ma_curr) and not partial_plan["active"] and price_diff > PRICE_THRESHOLD:
            if len(open_positions) < MAX_OPEN_TRADES:
                can_buy = True
                # Apply reentry gap check only if there are open positions
                if open_positions and last_buy_price is not None:
                    needed_price = last_buy_price * (1 - REENTRY_GAP_PERCENT / 100.0)
                    if current_price > needed_price:
                        can_buy = False

                if can_buy:
                    # Compute equity and set up trade value using Martingale logic
                    eq_now = compute_equity(balance, open_positions, current_price)
                    base_trade_value = eq_now * (POSITION_SIZE_PERCENT / 100.0)
                    
                    # Initialize next_trade_value if first order, else increase it by x%
                    if next_trade_value is None or not open_positions:
                        next_trade_value = base_trade_value
                    else:
                        next_trade_value *= (1 + INCREASE_X_PERCENT / 100.0)
                    
                    total_trade_value = min(next_trade_value, balance)

                    if total_trade_value > 0:
                        partial_plan["active"] = True
                        partial_plan["steps_left"] = ACCUMULATION_STEPS
                        partial_plan["remaining_value"] = total_trade_value

        # 8) Track maximum open positions
        current_open_positions = len(open_positions)
        if current_open_positions > max_open_positions:
            max_open_positions = current_open_positions

    # End of data loop
    final_price  = df["close"].iloc[-1]
    final_equity = compute_equity(balance, open_positions, final_price)
    equity_curve.append(final_equity)

    total_pnl = final_equity - INITIAL_BALANCE
    max_dd    = calculate_max_drawdown(equity_curve)

    # Buy & hold stats
    buy_and_hold_final_equity = buy_and_hold_curve[-1]
    buy_and_hold_total_pnl    = buy_and_hold_final_equity - INITIAL_BALANCE
    buy_and_hold_max_dd       = calculate_max_drawdown(buy_and_hold_curve)

    results = {
        "final_balance": balance,
        "final_equity": final_equity,
        "total_pnl": total_pnl,
        "max_drawdown": max_dd,
        "open_positions": open_positions,
        "closed_trades": closed_trades,
        "equity_curve": equity_curve,
        "max_open_positions": max_open_positions,
        "buy_and_hold_equity_curve": buy_and_hold_curve,
        "buy_and_hold_final_equity": buy_and_hold_final_equity,
        "buy_and_hold_total_pnl": buy_and_hold_total_pnl,
        "buy_and_hold_max_dd": buy_and_hold_max_dd
    }
    return results

########################
# MAIN SCRIPT WITH SEGMENTED EVALUATION
########################
def main():
    csv_files = [f for f in os.listdir(SINGLE_ASSET_FOLDER) if f.endswith(".csv")]
    if not csv_files:
        print(f"[ERROR] No CSV files found in {SINGLE_ASSET_FOLDER}")
        return

    data_csv = None
    for f in csv_files:
        path = os.path.join(SINGLE_ASSET_FOLDER, f)
        if is_valid_price_history_file(path):
            data_csv = path
            break

    if not data_csv:
        print("[ERROR] No valid price history CSV found in the folder.")
        return

    csv_path = os.path.join(SINGLE_ASSET_FOLDER, data_csv)
    print(f"[INFO] Using CSV file: {csv_path}")

    # Load and preprocess data
    df = pd.read_csv(
        csv_path,
        parse_dates=[CSV_TIMESTAMP_COL],
        dayfirst=True,
        low_memory=False
    )

    df[CSV_TIMESTAMP_COL] = pd.to_datetime(df[CSV_TIMESTAMP_COL], errors="coerce")
    df.dropna(subset=[CSV_TIMESTAMP_COL], inplace=True)
    df.rename(columns={CSV_TIMESTAMP_COL: "timestamp", CSV_CLOSE_COL: "close"}, inplace=True)
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)

    # Split data into three segments
    segment_length = len(df) // 3
    df1 = df.iloc[:segment_length].copy()
    df2 = df.iloc[segment_length:2*segment_length].copy()
    df3 = df.iloc[2*segment_length:].copy()

    # Run simulation on each segment
    print("[INFO] Running simulation on Segment 1...")
    result1 = backtest_partial_accumulation_with_dd_and_partial_sells(df1)
    print("[INFO] Running simulation on Segment 2...")
    result2 = backtest_partial_accumulation_with_dd_and_partial_sells(df2)
    print("[INFO] Running simulation on Segment 3...")
    result3 = backtest_partial_accumulation_with_dd_and_partial_sells(df3)

    # Compute average metrics for strategy
    avg_final_balance = (result1['final_balance'] + result2['final_balance'] + result3['final_balance']) / 3
    avg_final_equity  = (result1['final_equity']  + result2['final_equity']  + result3['final_equity'] ) / 3
    avg_total_pnl     = (result1['total_pnl']     + result2['total_pnl']     + result3['total_pnl']    ) / 3
    avg_max_drawdown  = (result1['max_drawdown']  + result2['max_drawdown']  + result3['max_drawdown'] ) / 3

    # Compute average metrics for buy & hold
    avg_bh_final_equity = (result1['buy_and_hold_final_equity'] + result2['buy_and_hold_final_equity'] + result3['buy_and_hold_final_equity']) / 3
    avg_bh_total_pnl    = (result1['buy_and_hold_total_pnl']    + result2['buy_and_hold_total_pnl']    + result3['buy_and_hold_total_pnl']) / 3
    avg_bh_max_dd       = (result1['buy_and_hold_max_dd']       + result2['buy_and_hold_max_dd']       + result3['buy_and_hold_max_dd']) / 3

    print("\n--- SEGMENT RESULTS ---")
    print(f"Segment 1 - Final Balance: {result1['final_balance']:.2f}, Total PnL: {result1['total_pnl']:.2f}, Max Drawdown: {result1['max_drawdown']:.2f}%")
    print(f"Segment 2 - Final Balance: {result2['final_balance']:.2f}, Total PnL: {result2['total_pnl']:.2f}, Max Drawdown: {result2['max_drawdown']:.2f}%")
    print(f"Segment 3 - Final Balance: {result3['final_balance']:.2f}, Total PnL: {result3['total_pnl']:.2f}, Max Drawdown: {result3['max_drawdown']:.2f}%")

    print("\n--- AVERAGE RESULTS ACROSS SEGMENTS ---")
    print(f"Average Final Balance: {avg_final_balance:.2f}")
    print(f"Average Final Equity : {avg_final_equity:.2f}")
    print(f"Average Total PnL    : {avg_total_pnl:.2f}")
    print(f"Average Max Drawdown : {avg_max_drawdown:.2f}%")

    print("\n--- AVERAGE BUY & HOLD RESULTS ACROSS SEGMENTS ---")
    print(f"Average Buy & Hold Final Equity: {avg_bh_final_equity:.2f}")
    print(f"Average Buy & Hold Total PnL   : {avg_bh_total_pnl:.2f}")
    print(f"Average Buy & Hold Max Drawdown: {avg_bh_max_dd:.2f}%")

if __name__ == "__main__":
    main()
