import yfinance as yf
import pandas as pd
import ta


def _flatten_columns(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).strip() for c in df.columns]
    # auto_adjust=True può aggiungere 'Adj Close': rinomina in Close se manca
    if "Close" not in df.columns and "Adj Close" in df.columns:
        df = df.rename(columns={"Adj Close": "Close"})
    return df


def fetch_all(tickers: list[str], period: str = "6mo") -> dict[str, pd.DataFrame]:
    """Scarica tutti i ticker in un'unica chiamata per evitare rate limit."""
    raw = yf.download(
        tickers,
        period=period,
        interval="1d",
        progress=False,
        auto_adjust=True,
        group_by="ticker",
    )

    result = {}

    if len(tickers) == 1:
        df = _flatten_columns(raw.copy(), tickers[0])
        df.dropna(subset=["Close"], inplace=True)
        if len(df) >= 30:
            result[tickers[0]] = df
        return result

    for ticker in tickers:
        try:
            df = raw[ticker].copy()
            df = _flatten_columns(df, ticker)
            df.dropna(subset=["Close"], inplace=True)
            if len(df) >= 30:
                result[ticker] = df
        except Exception:
            continue

    return result


def fetch_data(ticker: str, period: str = "6mo") -> pd.DataFrame:
    data = fetch_all([ticker], period)
    return data.get(ticker, pd.DataFrame())


def compute_indicators(df: pd.DataFrame) -> dict:
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    rsi = ta.momentum.RSIIndicator(close, window=14).rsi()
    cci = ta.trend.CCIIndicator(high, low, close, window=20).cci()
    macd_obj = ta.trend.MACD(close)
    macd_line = macd_obj.macd()
    macd_signal = macd_obj.macd_signal()
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    bb_upper = bb.bollinger_hband()
    bb_lower = bb.bollinger_lband()
    bb_mid = bb.bollinger_mavg()

    last_close = float(close.iloc[-1])
    last_rsi = float(rsi.iloc[-1])
    last_cci = float(cci.iloc[-1])
    last_macd = float(macd_line.iloc[-1])
    last_signal = float(macd_signal.iloc[-1])
    last_bb_lower = float(bb_lower.iloc[-1])
    last_bb_upper = float(bb_upper.iloc[-1])
    last_bb_mid = float(bb_mid.iloc[-1])

    avg_vol = float(volume.iloc[-21:-1].mean()) if len(volume) > 21 else float(volume.mean())
    last_vol = float(volume.iloc[-1])
    vol_ratio = last_vol / avg_vol if avg_vol > 0 else 1.0

    high_52 = float(close.tail(252).max())
    low_52 = float(close.tail(252).min())
    pct_from_high = ((last_close - high_52) / high_52) * 100
    pct_from_low = ((last_close - low_52) / low_52) * 100

    bb_range = last_bb_upper - last_bb_lower
    bb_pos = ((last_close - last_bb_lower) / bb_range * 100) if bb_range > 0 else 50

    return {
        "price": round(last_close, 4),
        "rsi": round(last_rsi, 2),
        "cci": round(last_cci, 2),
        "macd": round(last_macd, 4),
        "macd_signal": round(last_signal, 4),
        "macd_bullish": last_macd > last_signal,
        "bb_lower": round(last_bb_lower, 4),
        "bb_upper": round(last_bb_upper, 4),
        "bb_mid": round(last_bb_mid, 4),
        "bb_position": round(bb_pos, 1),
        "vol_ratio": round(vol_ratio, 2),
        "high_52w": round(high_52, 4),
        "low_52w": round(low_52, 4),
        "pct_from_high": round(pct_from_high, 2),
        "pct_from_low": round(pct_from_low, 2),
    }


def compute_score(ind: dict) -> int:
    """
    Score 0-100 da 5 indicatori tecnici convergenti.

    RSI  (0-25): ipervenduto < 30 = acquisto forte
    CCI  (0-25): sotto -200 = ipervenduto valido (soglia conservativa)
    BB   (0-20): prezzo vicino banda inferiore
    MACD (0-15): crossover bullish
    52W  (0-15): vicinanza al minimo annuale
    """
    score = 0

    rsi = ind["rsi"]
    if rsi < 30:
        score += 25
    elif rsi < 40:
        score += 18
    elif rsi < 50:
        score += 8

    cci = ind["cci"]
    if cci < -200:
        score += 25
    elif cci < -150:
        score += 10

    bb_pos = ind["bb_position"]
    if bb_pos < 10:
        score += 20
    elif bb_pos < 25:
        score += 13
    elif bb_pos < 40:
        score += 6

    if ind["macd_bullish"]:
        score += 15

    pct_from_low = ind["pct_from_low"]
    if pct_from_low < 5:
        score += 15
    elif pct_from_low < 15:
        score += 8
    elif pct_from_low < 25:
        score += 3

    return min(score, 100)


def signal_label(score: int) -> str:
    if score >= 70:
        return "FORTE ACQUISTO"
    elif score >= 50:
        return "ACQUISTO"
    elif score >= 30:
        return "NEUTRO"
    else:
        return "ATTENDI"


def signal_color(score: int) -> str:
    if score >= 70:
        return "#22c55e"
    elif score >= 50:
        return "#86efac"
    elif score >= 30:
        return "#fbbf24"
    else:
        return "#f87171"


def get_chart_data(ticker: str, period: str = "6mo") -> dict:
    df = fetch_data(ticker, period)
    if df.empty:
        return {}

    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    rsi_series = ta.momentum.RSIIndicator(close, window=14).rsi()
    cci_series = ta.trend.CCIIndicator(high, low, close, window=20).cci()
    macd_obj = ta.trend.MACD(close)
    macd_line = macd_obj.macd()
    macd_signal_line = macd_obj.macd_signal()
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)

    dates = [d.strftime("%Y-%m-%d") for d in df.index]

    def clean(series):
        return [round(float(v), 4) if pd.notna(v) else None for v in series]

    return {
        "dates": dates,
        "close": clean(close),
        "bb_upper": clean(bb.bollinger_hband()),
        "bb_lower": clean(bb.bollinger_lband()),
        "bb_mid": clean(bb.bollinger_mavg()),
        "rsi": clean(rsi_series),
        "cci": clean(cci_series),
        "macd": clean(macd_line),
        "macd_signal": clean(macd_signal_line),
    }


def analyze_all(assets: list, period: str = "6mo") -> list:
    tickers = [a["ticker"] for a in assets]
    asset_map = {a["ticker"]: a for a in assets}

    data_map = fetch_all(tickers, period)

    results = []
    for ticker, df in data_map.items():
        try:
            ind = compute_indicators(df)
            score = compute_score(ind)
            asset = asset_map[ticker]
            results.append({
                "ticker": ticker,
                "name": asset["name"],
                "category": asset["category"],
                "score": score,
                "signal": signal_label(score),
                "color": signal_color(score),
                **ind,
            })
        except Exception:
            continue

    results.sort(key=lambda x: x["score"], reverse=True)
    return results
