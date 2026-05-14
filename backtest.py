import pandas as pd
import ta
from analyzer import fetch_all

# Holding della posizione dopo il segnale, in giorni di borsa.
# Calibrato su 3 anni di storico (vedi calibrate.py): l'edge dei segnali long
# si manifesta su ~5 giorni, non sul giorno successivo.
HOLD_DAYS = 5


def _empty() -> dict:
    return {
        "signals": 0, "win_rate": 0, "avg_return": 0, "total_return": 0,
        "max_drawdown": 0, "best_trade": 0, "worst_trade": 0,
        "trades": [], "equity_curve": [],
    }


def backtest_asset(df: pd.DataFrame) -> dict:
    """
    Vectorized backtest of Alta Confidenza (>=5/7) on daily bars — no lookahead.
    Signal = at least 5 of 7 criteria from compute_rischio_basso satisfied.
    Holding = HOLD_DAYS giorni; segnali dentro una posizione aperta scartati.
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

    # Volume vs 10-day avg — shift(1) keeps prior 10 bars, no lookahead
    vol_avg   = volume.rolling(10, min_periods=5).mean().shift(1)
    vol_ratio = (volume / vol_avg).where(vol_avg > 0, 1.0).fillna(1.0)

    # Alta Confidenza — same 7 criteria as compute_rischio_basso, signal at >=5
    c1 = (rsi_s >= 30) & (rsi_s <= 45)
    c2 = (cci_s < -100) & (cci_s > cci_s.shift(1))
    c3 = (stoch_k < 20) & (stoch_k > stoch_k.shift(1))
    c4 = close > ema50_s
    c5 = vol_ratio > 1.0
    c6 = macd_hist > macd_hist.shift(1)
    c7 = bb_pos < 10

    score  = c1.astype(int) + c2.astype(int) + c3.astype(int) + c4.astype(int) + \
             c5.astype(int) + c6.astype(int) + c7.astype(int)
    signal = score >= 5
    fwd_ret = (close.shift(-HOLD_DAYS) / close - 1) * 100   # rendimento a HOLD_DAYS giorni
    valid   = signal & fwd_ret.notna()

    signal_idx = df.index[valid]
    if len(signal_idx) == 0:
        return _empty()

    trades       = []
    equity       = 1.0
    peak         = 1.0
    max_dd       = 0.0
    equity_curve = [{"time": str(df.index[0].date()), "value": 1.0}]

    last_exit = -1
    for idx in signal_idx:
        pos = df.index.get_loc(idx)
        if pos >= len(df) - HOLD_DAYS:
            continue
        if pos <= last_exit:          # segnale dentro una posizione gia' aperta
            continue
        exit_pos  = pos + HOLD_DAYS
        last_exit = exit_pos
        entry = float(close.iloc[pos])
        exit_ = float(close.iloc[exit_pos])
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
            "time":  df.index[exit_pos].strftime("%Y-%m-%d"),
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


def backtest_short_asset(df: pd.DataFrame) -> dict:
    """
    Vectorized backtest of SHORT signal (>=5/7) on daily bars — no lookahead.
    Holding = HOLD_DAYS giorni. Profitto se il prezzo scende.
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

    vol_avg   = volume.rolling(10, min_periods=5).mean().shift(1)
    vol_ratio = (volume / vol_avg).where(vol_avg > 0, 1.0).fillna(1.0)

    # SHORT — mirror of compute_short, signal at >=5
    c1 = (rsi_s > 65)  & (rsi_s   < rsi_s.shift(1))       # RSI>65 falling
    c2 = (cci_s > 200) & (cci_s   < cci_s.shift(1))       # CCI>+200 falling
    c3 = (stoch_k > 80) & (stoch_k < stoch_k.shift(1))    # StochK>80 falling
    c4 = close < ema50_s                                    # price < EMA50
    c5 = vol_ratio > 1.0                                    # volume > average
    c6 = macd_hist < macd_hist.shift(1)                    # MACD negative divergence
    c7 = bb_pos > 90                                        # price near upper band

    score  = c1.astype(int) + c2.astype(int) + c3.astype(int) + c4.astype(int) + \
             c5.astype(int) + c6.astype(int) + c7.astype(int)
    signal = score >= 5

    fwd_ret = (close.shift(-HOLD_DAYS) / close - 1) * 100
    valid   = signal & fwd_ret.notna()

    signal_idx = df.index[valid]
    if len(signal_idx) == 0:
        return _empty()

    trades       = []
    equity       = 1.0
    peak         = 1.0
    max_dd       = 0.0
    equity_curve = [{"time": str(df.index[0].date()), "value": 1.0}]

    last_exit = -1
    for idx in signal_idx:
        pos = df.index.get_loc(idx)
        if pos >= len(df) - HOLD_DAYS:
            continue
        if pos <= last_exit:          # segnale dentro una posizione gia' aperta
            continue
        exit_pos  = pos + HOLD_DAYS
        last_exit = exit_pos
        entry = float(close.iloc[pos])
        exit_ = float(close.iloc[exit_pos])
        ret   = -((exit_ - entry) / entry * 100)   # short: profitto se il prezzo scende

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
            "time":  df.index[exit_pos].strftime("%Y-%m-%d"),
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
    tickers       = [a["ticker"] for a in assets]
    short_tickers = {a["ticker"] for a in assets if a.get("short_enabled")}
    data_map      = fetch_all(tickers, "3y")
    results       = {}
    for ticker, df in data_map.items():
        try:
            long_bt  = backtest_asset(df)
            short_bt = backtest_short_asset(df) if ticker in short_tickers else None
            results[ticker] = {**long_bt, "short": short_bt}
        except Exception:
            results[ticker] = {**_empty(), "short": None}
    return results
