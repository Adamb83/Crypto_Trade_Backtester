
Some of my backtesting frameworks for testing moving average crossovers on large amounts of historic price data.

Crypto_Trade_Backtest.py  Uses multiprocessing to test many different parameters of moving average crossovers and some other simple logic. It will continually run on however many csv's are in the folder. It will give an overview of the most profitable settings overall to avoid overfitted strategies, the way it aggregates the results probably needs some work also needs drawdown inclusion for filtering purposes. 

Crypto_Trade_Backtest.py will be modified to include the logic of Backtest_MA_Crossover.py 

Crypto_Trade_Backtest_Overfitted.py Generates the most overfitted MA cross just for research and ideas.






