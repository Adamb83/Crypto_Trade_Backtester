
Some of my backtesting frameworks for testing moving average crossovers on large amounts of historic price data.

Crypto_Trade_Backtest.py  Uses multiprocessing to test many different parameters of moving average crossovers and some other simple logic. 

It will continually run on however many csv's are in the folder. 

It will give an overview of the most profitable settings overall to avoid overfitted strategies, the way it aggregates the results probably needs some work also needs drawdown inclusion for filtering purposes. 

Extremely resource intensive script. I use 20 cores to run it..

The random sample segments of massive data sets (1000's of csv's) can potentially help develop strategies for your own trading logic that are NOT overfitted.







