Crypto_Trade_Backtest.py
A Python-based framework for back testing and optimizing cryptocurrency trading strategies using historical data.

Trade Logic is super simple at present and ready to build on.
Buying when the short moving average crosses above the long moving average, provided the RSI is below a specified threshold and selling when the short moving average crosses below the long moving average.
So trend following/swing trade framework. 

It needs addition of Supertrend, Drawdown, Sharpe ratio, Buy N Hold Comaparison and few other bits and bobs..


Get_Historical_Data.py
 
Fetches data for up to 300 coins by default.
Configurable to support different timeframes and intervals.
Saves historical data as CSV files for backtesting.
Use Case:
Prepares historical price data for use in the backtesting scripts.

Crypto_Trade_Backtest_Overfit.py

Identifies the most profitable trading strategy for a single cryptocurrency asset.
Implements moving averages (SMA, EMA) and RSI as trading indicators.
Tests all combinations of indicator settings over the entire historical dataset for one coin.
Outputs the best-performing settings for the tested asset.

Ideal for detailed optimization of a single coin, though results may be overfitted to the historical data.

Crypto_Trade_Backtest.py

Tests trading strategies across multiple cryptocurrencies using randomized intervals to improve robustness.
Implements Randomized Interval Backtesting, which selects random start and end times for testing.
Evaluates strategy performance over multiple iterations to identify robust configurations.
Combines results across all tested coins to rank the best-performing settings.
Outputs aggregated results and ranked strategies based on profitability.

Designed to find strategies that perform well across a range of conditions and multiple assets.
Multi-Coin Backtesting, evaluate strategies across multiple assets in one go.

Overfitted Strategy Builder
Use the single-asset backtester (Crypto_Trade_Backtest_Overfit.py) to fine-tune individual strategies.

Robustness Testing
Apply Crypto_Trade_Backtest.py to identify strategies that are likely to generalize well, avoiding overfitting.

Backtest for Single Asset Optimization:
Use Crypto_Trade_Backtest_Overfit.py to analyze and optimize strategies for a specific asset. Results will be the most overfitted settings.

Run Crypto_Trade_Backtest.py to evaluate strategies across multiple coins (100's) and random intervals.
Run Randomized Interval Backtesting across any number of coins, however many are in the dir it will use. 
End result is the opposite of an overfitted strategy, you get the best settings across all assets tested.
This backtes uses parallel processing, you can manually set a max number of cores available if you like.

Everyone learning about swing trading can definetely benefit from automatically testing their settings across 100s of different assets at once.







