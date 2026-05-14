"""
Strumento di calibrazione segnali — NON parte con l'app, si lancia a mano:
    python calibrate.py

Testa varianti di:
  - cutoff: quanti dei 7 criteri devono essere soddisfatti (4, 5, 6)
  - holding: per quanti giorni si tiene la posizione dopo il segnale (1, 3, 5)

Misura, sullo storico 3 anni daily, il rendimento forward medio condizionato al segnale.
Riporta i risultati su TUTTI gli asset e solo sul DAX, cosi' si vede se una
configurazione e' robusta in generale o solo fortunata sul DAX.

ATTENZIONE: calibrare sullo storico riduce le scelte palesemente sbagliate,
non predice il futuro. Niente grid-search aggressivo: solo parametri con un
senso (numero di conferme, durata della posizione) per limitare l'overfitting.
"""
import pandas as pd
import ta
from analyzer import fetch_all
from assets import ASSETS

# Bande standard dei criteri — tenute fisse (toccare queste = rischio overfit alto).
LONG = dict(rsi_lo=30, rsi_hi=45, cci_max=-100, stoch_max=20, bb_max=10, vol_min=1.0)
SHORT = dict(rsi_min=65, cci_min=200, stoch_min=80, bb_min=90, vol_min=1.0)


def _indicators(df: pd.DataFrame) -> dict:
    """Indicatori vettoriali, nessun lookahead."""
    close, high, low, volume = df["Close"], df["High"], df["Low"], df["Volume"]
    rsi   = ta.momentum.RSIIndicator(close, window=14).rsi()
    cci   = ta.trend.CCIIndicator(high, low, close, window=14).cci()
    mhist = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9).macd_diff()
    bb    = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    ema50 = ta.trend.EMAIndicator(close, window=50).ema_indicator()
    stoch = ta.momentum.StochRSIIndicator(close, window=14, smooth1=3, smooth2=3).stochrsi_k() * 100
    bb_lo, bb_hi = bb.bollinger_lband(), bb.bollinger_hband()
    bb_rng = bb_hi - bb_lo
    bb_pos = ((close - bb_lo) / bb_rng * 100).where(bb_rng > 0, 50.0)
    vol_avg = volume.rolling(10, min_periods=5).mean().shift(1)
    vol_ratio = (volume / vol_avg).where(vol_avg > 0, 1.0).fillna(1.0)
    return dict(close=close, rsi=rsi, cci=cci, mhist=mhist,
                ema50=ema50, stoch=stoch, bb_pos=bb_pos, vol_ratio=vol_ratio)


def _long_score(I: dict) -> pd.Series:
    c1 = (I["rsi"] >= LONG["rsi_lo"]) & (I["rsi"] <= LONG["rsi_hi"])
    c2 = (I["cci"] < LONG["cci_max"]) & (I["cci"] > I["cci"].shift(1))
    c3 = (I["stoch"] < LONG["stoch_max"]) & (I["stoch"] > I["stoch"].shift(1))
    c4 = I["close"] > I["ema50"]
    c5 = I["vol_ratio"] > LONG["vol_min"]
    c6 = I["mhist"] > I["mhist"].shift(1)
    c7 = I["bb_pos"] < LONG["bb_max"]
    return sum(c.astype(int) for c in [c1, c2, c3, c4, c5, c6, c7])


def _short_score(I: dict) -> pd.Series:
    c1 = (I["rsi"] > SHORT["rsi_min"]) & (I["rsi"] < I["rsi"].shift(1))
    c2 = (I["cci"] > SHORT["cci_min"]) & (I["cci"] < I["cci"].shift(1))
    c3 = (I["stoch"] > SHORT["stoch_min"]) & (I["stoch"] < I["stoch"].shift(1))
    c4 = I["close"] < I["ema50"]
    c5 = I["vol_ratio"] > SHORT["vol_min"]
    c6 = I["mhist"] < I["mhist"].shift(1)
    c7 = I["bb_pos"] > SHORT["bb_min"]
    return sum(c.astype(int) for c in [c1, c2, c3, c4, c5, c6, c7])


def _forward_returns(score: pd.Series, close: pd.Series, cutoff: int, hold: int, short: bool) -> list:
    """Rendimento % a `hold` giorni dopo ogni segnale (score >= cutoff)."""
    fwd = (close.shift(-hold) / close - 1) * 100
    if short:
        fwd = -fwd
    valid = (score >= cutoff) & fwd.notna()
    return fwd[valid].tolist()


def _stats(rets: list) -> dict:
    if not rets:
        return dict(n=0, win=0.0, avg=0.0, med=0.0)
    wins = sum(1 for r in rets if r > 0)
    s = sorted(rets)
    med = s[len(s) // 2]
    return dict(n=len(rets), win=round(wins / len(rets) * 100, 1),
                avg=round(sum(rets) / len(rets), 2), med=round(med, 2))


def _row(label: str, all_rets: list, dax_rets: list) -> str:
    a, d = _stats(all_rets), _stats(dax_rets)
    return (f"  {label:<22} | TUTTI: n={a['n']:>4}  win={a['win']:>5}%  "
            f"avg={a['avg']:>+6}%  med={a['med']:>+6}% "
            f"| DAX: n={d['n']:>3}  win={d['win']:>5}%  avg={d['avg']:>+6}%")


def run():
    tickers = [a["ticker"] for a in ASSETS]
    dax = {a["ticker"] for a in ASSETS if a["category"] == "DAX"}
    print("Scarico 3 anni daily per", len(tickers), "asset...")
    data = fetch_all(tickers, "3y")
    indick = {t: _indicators(df) for t, df in data.items() if len(df) >= 150}
    print("Asset con storico sufficiente:", len(indick),
          "| di cui DAX:", len([t for t in indick if t in dax]))
    print()

    for side, score_fn, is_short in [("LONG", _long_score, False), ("SHORT", _short_score, True)]:
        print(f"=== {side} ===  (baseline attuale = cutoff>=5, hold=1g)")
        scores = {t: score_fn(I) for t, I in indick.items()}
        for cutoff in (4, 5, 6):
            for hold in (1, 3, 5):
                all_rets, dax_rets = [], []
                for t, I in indick.items():
                    rets = _forward_returns(scores[t], I["close"], cutoff, hold, is_short)
                    all_rets += rets
                    if t in dax:
                        dax_rets += rets
                tag = "  <- baseline" if (cutoff == 5 and hold == 1) else ""
                print(_row(f"cutoff>={cutoff}  hold={hold}g", all_rets, dax_rets) + tag)
        print()


if __name__ == "__main__":
    run()
