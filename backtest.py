import pandas as pd
import ta
from analyzer import fetch_all


def _empty() -> dict:
    return {
        "signals": 0, "win_rate": 0, "avg_return": 0, "total_return": 0,
        "max_drawdown": 0, "best_trade": 0, "worst_trade": 0,
        "trades": [], "equity_curve": [],
    }


def backtest_asset(df: pd.DataFrame) -> dict:
    """
    Vectorized backtest of Alta Confidenza (7/7) on weekly bars — no lookahead.
    Signal = all 7 criteria from compute_rischio_basso satisfied simultaneously.
    Measures next-week return after each signal.
    """
    if len(df) < 55:
        return _empty()

    close  = df["Close"]
    high   = df["High"]
    low    = df["Low"]
    volume = df["Volume"]

    rsi_s    = ta.momentum.RSIIndicator(close, window=14).rsi()
    cci_s    = ta.trend.CCIIndicator(high, low, close, window=14).cci()
    macd_o   = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
    bb       = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    ema50_s  = ta.trend.EMAIndicator(close, window=50).ema_indicator()
    stoch_o  = ta.momentum.StochRSIIndicator(close, window=14, smooth1=3, smooth2=3)

    stoch_k   = stoch_o.stochrsi_k() * 100
    macd_hist = macd_o.macd_diff()
    bb_lower  = bb.bollinger_lband()
    bb_upper  = bb.bollinger_hband()
    bb_range  = bb_upper - bb_lower
    bb_pos    = ((close - bb_lower) / bb_range * 100).where(bb_range > 0, 50.0)

    # Volume vs 10-week avg — shift(1) keeps prior 10 bars, no lookahead
    vol_avg   = volume.rolling(10, min_periods=5).mean().shift(1)
    vol_ratio = (volume / vol_avg).where(vol_avg > 0, 1.0).fillna(1.0)

    # Alta Confidenza — same 7 criteria as compute_rischio_basso
    c1 = (rsi_s >= 30) & (rsi_s <= 45)
    c2 = (cci_s < -100) & (cci_s > cci_s.shift(1))
    c3 = (stoch_k < 20) & (stoch_k > stoch_k.shift(1))
    c4 = close > ema50_s
    c5 = vol_ratio > 1.0
    c6 = macd_hist > macd_hist.shift(1)
    c7 = bb_pos < 10

    signal   = c1 & c2 & c3 & c4 & c5 & c6 & c7
    next_ret = close.pct_change().shift(-1) * 100   # next-bar return, no lookahead
    valid    = signal & next_ret.notna()

    signal_idx = df.index[valid]
    if len(signal_idx) == 0:
        return _empty()

    trades       = []
    equity       = 1.0
    peak         = 1.0
    max_dd       = 0.0
    equity_curve = [{"time": str(df.index[0].date()), "value": 1.0}]

    for idx in signal_idx:
        pos   = df.index.get_loc(idx)
        if pos >= len(df) - 1:
            continue
        entry = float(close.iloc[pos])
        exit_ = float(close.iloc[pos + 1])
        ret   = (exit_ - entry) / entry * 100

        equity *= 1 + ret / 100
        peak    = max(peak, equity)
        dd      = (equity - peak) / peak * 100
        max_dd  = min(max_dd, dd)

        trades.append({
            "date":  df.index[pos].strftime("%Y-%m-%d"),
            "entry": round(entry, 4),
            "exit":  round(exit_, 4),
            "ret":   round(ret, 2),
        })
        equity_curve.append({
            "time":  df.index[pos + 1].strftime("%Y-%m-%d"),
            "value": round(equity, 4),
        })

    if not trades:
        return _empty()

    rets = [t["ret"] for t in trades]
    wins = sum(1 for r in rets if r > 0)

    return {
        "signals":      len(trades),
        "win_rate":     round(wins / len(trades) * 100, 1),
        "avg_return":   round(sum(rets) / len(rets), 2),
        "total_return": round((equity - 1) * 100, 2),
        "max_drawdown": round(max_dd, 2),
        "best_trade":   round(max(rets), 2),
        "worst_trade":  round(min(rets), 2),
        "trades":       trades,
        "equity_curve": equity_curve,
    }


def backtest_all(assets: list) -> dict:
    tickers  = [a["ticker"] for a in assets]
    data_map = fetch_all(tickers, "3y")
    results  = {}
    for ticker, df in data_map.items():
        try:
            results[ticker] = backtest_asset(df)
        except Exception:
            results[ticker] = _empty()
    return results
