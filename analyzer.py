import yfinance as yf
import pandas as pd
import ta


def fetch_all(tickers: list[str], period: str = "6mo") -> dict[str, pd.DataFrame]:
    """Single batch download — no group_by to avoid column structure issues."""
    try:
        raw = yf.download(
            tickers,
            period=period,
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
    except Exception:
        return {}

    if raw.empty:
        return {}

    result = {}

    if len(tickers) == 1:
        df = raw.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).strip() for c in df.columns]
        if "Close" not in df.columns and "Adj Close" in df.columns:
            df.rename(columns={"Adj Close": "Close"}, inplace=True)
        df.dropna(subset=["Close"], inplace=True)
        if len(df) >= 15:
            result[tickers[0]] = df
        return result

    # Multiple tickers: raw has MultiIndex columns (price_type, ticker)
    for ticker in tickers:
        try:
            df = pd.DataFrame({
                "Open":   raw["Open"][ticker],
                "High":   raw["High"][ticker],
                "Low":    raw["Low"][ticker],
                "Close":  raw["Close"][ticker],
                "Volume": raw["Volume"][ticker],
            }).dropna(subset=["Close"])
            if len(df) >= 15:
                result[ticker] = df
        except Exception:
            continue

    return result


def fetch_data(ticker: str, period: str = "6mo") -> pd.DataFrame:
    return fetch_all([ticker], period).get(ticker, pd.DataFrame())


def _clean(series, scale: float = 1.0) -> list:
    return [round(float(v) * scale, 4) if pd.notna(v) else None for v in series]


def compute_indicators(df: pd.DataFrame) -> dict:
    close  = df["Close"]
    high   = df["High"]
    low    = df["Low"]
    volume = df["Volume"]

    rsi_s   = ta.momentum.RSIIndicator(close, window=14).rsi()
    cci_s   = ta.trend.CCIIndicator(high, low, close, window=20).cci()
    macd_o  = ta.trend.MACD(close)
    bb      = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    ema20_s = ta.trend.EMAIndicator(close, window=20).ema_indicator()
    ema50_s = ta.trend.EMAIndicator(close, window=50).ema_indicator()
    ema200_s= ta.trend.EMAIndicator(close, window=200).ema_indicator()
    stoch_o = ta.momentum.StochRSIIndicator(close, window=14, smooth1=3, smooth2=3)
    atr_s   = ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range()

    def last(s):
        v = s.iloc[-1]
        return float(v) if pd.notna(v) else None

    price      = last(close)
    rsi        = last(rsi_s)
    cci        = last(cci_s)
    macd       = last(macd_o.macd())
    macd_sig   = last(macd_o.macd_signal())
    bb_lower   = last(bb.bollinger_lband())
    bb_upper   = last(bb.bollinger_hband())
    bb_mid     = last(bb.bollinger_mavg())
    ema20      = last(ema20_s)
    ema50      = last(ema50_s)
    ema200     = last(ema200_s)
    stoch_k    = last(stoch_o.stochrsi_k())
    stoch_d    = last(stoch_o.stochrsi_d())
    atr        = last(atr_s)

    avg_vol  = float(volume.iloc[-21:-1].mean()) if len(volume) > 21 else float(volume.mean())
    vol_ratio = float(volume.iloc[-1]) / avg_vol if avg_vol > 0 else 1.0

    # usa tutto il range scaricato (varia con il periodo selezionato)
    high_52 = float(close.max())
    low_52  = float(close.min())
    pct_from_high = ((price - high_52) / high_52) * 100
    pct_from_low  = ((price - low_52)  / low_52)  * 100

    bb_range = (bb_upper or 0) - (bb_lower or 0)
    bb_pos   = ((price - bb_lower) / bb_range * 100) if bb_range > 0 else 50

    macd_bullish  = (macd or 0) > (macd_sig or 0)
    ema_bullish   = (ema20 or 0) > (ema50 or 0)
    golden_cross  = ema200 is not None and (ema20 or 0) > (ema50 or 0) > ema200
    stoch_k_pct   = (stoch_k or 0.5) * 100
    stoch_d_pct   = (stoch_d or 0.5) * 100

    # --- valori penultima barra per rilevare "in risalita" ---
    def prev(s):
        v = s.iloc[-2] if len(s) >= 2 else s.iloc[-1]
        return float(v) if pd.notna(v) else None

    cci_prev      = prev(cci_s)
    stoch_k_prev  = (prev(stoch_o.stochrsi_k()) or 0.5) * 100
    macd_hist_s   = macd_o.macd_diff()
    macd_hist_now = float(macd_hist_s.iloc[-1]) if pd.notna(macd_hist_s.iloc[-1]) else 0
    macd_hist_prv = float(macd_hist_s.iloc[-2]) if len(macd_hist_s) >= 2 and pd.notna(macd_hist_s.iloc[-2]) else 0

    cci_rising          = (cci or 0) > (cci_prev or 0)
    stoch_rising        = stoch_k_pct > stoch_k_prev
    macd_div_positive   = macd_hist_now > macd_hist_prv   # istogramma in crescita
    price_above_ema200  = ema200 is not None and price > ema200

    return {
        "price":              round(price, 4),
        "rsi":                round(rsi or 50, 2),
        "cci":                round(cci or 0, 2),
        "cci_rising":         cci_rising,
        "macd":               round(macd or 0, 6),
        "macd_signal":        round(macd_sig or 0, 6),
        "macd_bullish":       macd_bullish,
        "macd_div_positive":  macd_div_positive,
        "bb_lower":           round(bb_lower or 0, 4),
        "bb_upper":           round(bb_upper or 0, 4),
        "bb_mid":             round(bb_mid or 0, 4),
        "bb_position":        round(bb_pos, 1),
        "ema20":              round(ema20 or 0, 4),
        "ema50":              round(ema50 or 0, 4),
        "ema200":             round(ema200, 4) if ema200 else None,
        "golden_cross":       golden_cross,
        "ema_bullish":        ema_bullish,
        "price_above_ema200": price_above_ema200,
        "stoch_k":            round(stoch_k_pct, 2),
        "stoch_d":            round(stoch_d_pct, 2),
        "stoch_rising":       stoch_rising,
        "atr":                round(atr or 0, 4),
        "atr_pct":            round(((atr or 0) / price) * 100, 2),
        "vol_ratio":          round(vol_ratio, 2),
        "high_52w":           round(high_52, 4),
        "low_52w":            round(low_52, 4),
        "pct_from_high":      round(pct_from_high, 2),
        "pct_from_low":       round(pct_from_low, 2),
    }


def compute_semaforo(ind: dict) -> dict:
    """
    7 condizioni di acquisto. Verde=4+, Giallo=2-3, Rosso=0-1.
    """
    conds = {
        "RSI<40":     ind["rsi"] < 40,
        "CCI<-100":   ind["cci"] < -100,
        "MACD":       ind["macd_bullish"],
        "BB<30%":     ind["bb_position"] < 30,
        "EMA bull":   ind["ema_bullish"],
        "StochK<20":  ind["stoch_k"] < 20,
        "Vol×1.5":    ind["vol_ratio"] > 1.5,
    }
    count = sum(conds.values())
    if count >= 4:
        return {"level": "green",  "color": "#22c55e", "label": "COMPRA",  "count": count, "details": conds}
    elif count >= 2:
        return {"level": "yellow", "color": "#fbbf24", "label": "NEUTRO",  "count": count, "details": conds}
    else:
        return {"level": "red",    "color": "#ef4444", "label": "ATTENDI", "count": count, "details": conds}


def compute_rischio_basso(ind: dict) -> dict:
    """
    7 criteri specifici per segnale di entrata a basso rischio.
    7/7 -> Alta Confidenza, 6/7 -> Rischio Basso, <=5 -> nessun pulsante.
    """
    criteria = {
        "RSI 30-45":          30 <= ind["rsi"] <= 45,
        "CCI<-100 risalita":  ind["cci"] < -100 and ind["cci_rising"],
        "StochK<20 risalita": ind["stoch_k"] < 20 and ind["stoch_rising"],
        "Prezzo > EMA200":    ind["price_above_ema200"],
        "Volume > media":     ind["vol_ratio"] > 1.0,
        "MACD div. positiva": ind["macd_div_positive"],
        "BB banda inferiore": ind["bb_position"] < 10,
    }
    count = sum(criteria.values())
    if count == 7:
        return {"show": True,  "level": "alta",  "label": "Alta Confidenza", "count": count, "criteria": criteria}
    elif count == 6:
        return {"show": True,  "level": "basso", "label": "Rischio Basso",   "count": count, "criteria": criteria}
    else:
        return {"show": False, "level": "none",  "label": "",                "count": count, "criteria": criteria}


def compute_score(ind: dict) -> int:
    score = 0
    rsi = ind["rsi"]
    if rsi < 30:   score += 25
    elif rsi < 40: score += 18
    elif rsi < 50: score += 8
    cci = ind["cci"]
    if cci < -200:   score += 25
    elif cci < -150: score += 10
    bb = ind["bb_position"]
    if bb < 10:   score += 20
    elif bb < 25: score += 13
    elif bb < 40: score += 6
    if ind["macd_bullish"]: score += 15
    pl = ind["pct_from_low"]
    if pl < 5:   score += 15
    elif pl < 15: score += 8
    elif pl < 25: score += 3
    return min(score, 100)


def signal_label(score: int) -> str:
    if score >= 70: return "FORTE ACQUISTO"
    if score >= 50: return "ACQUISTO"
    if score >= 30: return "NEUTRO"
    return "ATTENDI"


def signal_color(score: int) -> str:
    if score >= 70: return "#22c55e"
    if score >= 50: return "#86efac"
    if score >= 30: return "#fbbf24"
    return "#f87171"


def get_chart_data(ticker: str, period: str = "6mo") -> dict:
    df = fetch_data(ticker, period)
    if df.empty:
        return {}

    close  = df["Close"]
    high   = df["High"]
    low    = df["Low"]
    open_  = df["Open"]
    volume = df["Volume"]

    rsi_s    = ta.momentum.RSIIndicator(close, window=14).rsi()
    cci_s    = ta.trend.CCIIndicator(high, low, close, window=20).cci()
    macd_o   = ta.trend.MACD(close)
    bb       = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    ema20_s  = ta.trend.EMAIndicator(close, window=20).ema_indicator()
    ema50_s  = ta.trend.EMAIndicator(close, window=50).ema_indicator()
    ema200_s = ta.trend.EMAIndicator(close, window=200).ema_indicator()
    stoch_o  = ta.momentum.StochRSIIndicator(close, window=14, smooth1=3, smooth2=3)
    vol_ma20 = volume.rolling(20).mean()

    dates = [d.strftime("%Y-%m-%d") for d in df.index]

    ohlcv = []
    for i, date in enumerate(dates):
        o, h, l, c = open_.iloc[i], high.iloc[i], low.iloc[i], close.iloc[i]
        if all(pd.notna(x) for x in [o, h, l, c]):
            ohlcv.append({"time": date,
                          "open":  round(float(o), 4),
                          "high":  round(float(h), 4),
                          "low":   round(float(l), 4),
                          "close": round(float(c), 4)})

    vol_data = [{"time": dates[i], "value": int(volume.iloc[i]),
                 "color": "#6366f180"} for i in range(len(dates)) if pd.notna(volume.iloc[i])]

    macd_hist_raw = macd_o.macd_diff()
    macd_hist = [{"time": dates[i],
                  "value": round(float(macd_hist_raw.iloc[i]), 6),
                  "color": "#22c55e" if (pd.notna(macd_hist_raw.iloc[i]) and macd_hist_raw.iloc[i] >= 0) else "#ef4444"}
                 for i in range(len(dates)) if pd.notna(macd_hist_raw.iloc[i])]

    def ts(series):
        return [{"time": dates[i], "value": round(float(series.iloc[i]), 4)}
                for i in range(len(dates)) if pd.notna(series.iloc[i])]

    def ts_pct(series, scale=100):
        return [{"time": dates[i], "value": round(float(series.iloc[i]) * scale, 2)}
                for i in range(len(dates)) if pd.notna(series.iloc[i])]

    return {
        "ohlcv":        ohlcv,
        "volume":       vol_data,
        "vol_ma20":     ts(vol_ma20),
        "bb_upper":     ts(bb.bollinger_hband()),
        "bb_lower":     ts(bb.bollinger_lband()),
        "bb_mid":       ts(bb.bollinger_mavg()),
        "ema20":        ts(ema20_s),
        "ema50":        ts(ema50_s),
        "ema200":       ts(ema200_s),
        "rsi":          ts(rsi_s),
        "cci":          ts(cci_s),
        "macd":         ts(macd_o.macd()),
        "macd_signal":  ts(macd_o.macd_signal()),
        "macd_hist":    macd_hist,
        "stoch_k":      ts_pct(stoch_o.stochrsi_k()),
        "stoch_d":      ts_pct(stoch_o.stochrsi_d()),
    }


def analyze_all(assets: list, period: str = "6mo") -> list:
    tickers   = [a["ticker"] for a in assets]
    asset_map = {a["ticker"]: a for a in assets}
    data_map  = fetch_all(tickers, period)

    results = []
    for ticker, df in data_map.items():
        try:
            ind           = compute_indicators(df)
            score         = compute_score(ind)
            semaforo      = compute_semaforo(ind)
            rischio_basso = compute_rischio_basso(ind)
            asset         = asset_map[ticker]
            results.append({
                "ticker":        ticker,
                "name":          asset["name"],
                "category":      asset["category"],
                "score":         score,
                "signal":        signal_label(score),
                "signal_color":  signal_color(score),
                "semaforo":      semaforo,
                "rischio_basso": rischio_basso,
                **ind,
            })
        except Exception:
            continue

    results.sort(key=lambda x: x["score"], reverse=True)
    return results
