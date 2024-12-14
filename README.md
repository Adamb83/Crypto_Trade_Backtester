# Crypto_Trade_Backtester
A Python-based framework for back testing and optimizing cryptocurrency trading strategies using historical data.

Trade Logic is super simple ready to build on to.
Buying when the short moving average crosses above the long moving average, provided the RSI is below a specified threshold and selling when the short moving average crosses below the long moving average.
So trend following/swing trade framework.

File Overview
1. Get_Historical_Data.py
Purpose:
Retrieves and saves historical OHLC data for cryptocurrencies.
Key Features:
Fetches data for up to 300 coins by default.
Configurable to support different timeframes and intervals.
Saves historical data as CSV files for backtesting.
Use Case:
Prepares historical price data for use in the backtesting scripts.

3. Crypto_Trade_Backtest_Overfit.py
Purpose:
Identifies the most profitable trading strategy for a single cryptocurrency asset.
Key Features:
Implements moving averages (SMA, EMA) and RSI as trading indicators.
Tests all combinations of indicator settings over the entire historical dataset for one coin.
Outputs the best-performing settings for the tested asset.
Use Case:
Ideal for detailed optimization of a single coin, though results may be overfitted to the historical data.

5. Crypto_Trade_Backtest.py
Purpose:
Tests trading strategies across multiple cryptocurrencies using randomized intervals to improve robustness.
Key Features:
Implements Randomized Interval Backtesting, which selects random start and end times for testing.
Evaluates strategy performance over multiple iterations to identify robust configurations.
Combines results across all tested coins to rank the best-performing settings.
Outputs aggregated results and ranked strategies based on profitability.
Use Case:
Designed to find strategies that perform well across a range of conditions and multiple assets.
Highlights
Multi-Coin Backtesting:
Evaluate strategies across multiple assets in one go.

Overfitted Strategy Builder:
Use the single-asset backtester (Crypto_Trade_Backtest_Overfit.py) to fine-tune individual strategies.

Robustness Testing:
Apply Crypto_Trade_Backtest.py to identify strategies that are likely to generalize well, avoiding overfitting.

Historical Data Retrieval:
Fetch and save data for backtesting with Get_Historical_Data.py.

Customizable Settings:
Fine-tune random iteration settings.

Example Workflows
1. Optimize for a Single Asset

Run Get_Historical_Data.py to fetch historical data.
Use Crypto_Trade_Backtest_Overfit.py to determine the most profitable settings for a specific coin.
2. Test Robustness Across Assets

Fetch data using Get_Historical_Data.py.
Run Crypto_Trade_Backtest.py to evaluate strategies across multiple coins and random intervals.
3. Prepare Historical Data

Use Get_Historical_Data.py to retrieve data for up to 300 coins and store it locally in CSV format.

Backtest for Single Asset Optimization:
Use Crypto_Trade_Backtest_Overfit.py to analyze and optimize strategies for a specific asset.

Run Randomized Interval Backtesting:
Run Crypto_Trade_Backtest.py to test strategies across multiple coins and random time intervals.

Fun learnings with these!





