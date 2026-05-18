"""
Gamma Exposure (GEX) — Call Wall / Put Wall — interamente via yfinance.

Per il DAX (^GDAXI) usiamo EWG (iShares MSCI Germany ETF, listato NYSE)
come proxy: la chain di EWG è esposta da yfinance, quella ODAX di Eurex no.
Correlazione DAX/EWG storicamente ~0.95.

I livelli calcolati su EWG vengono riproiettati sul piano DAX moltiplicando
per il rapporto spot DAX/EWG, così le linee sul grafico DAX sono leggibili.

Costo: zero. Nessun broker, nessun feed a pagamento.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime

import yfinance as yf
import pandas as pd


# ─── CONFIG ──────────────────────────────────────────────────────────────────

# Mapping ticker → underlying con chain Yahoo disponibile.
# Quando proxy != ticker, i livelli del proxy vengono riproiettati sul piano
# del ticker richiesto via ratio spot (etichetta onesta nel badge UI).
# Solo ticker di tipo "indice/ETF/future" — su azioni singole il GEX è poco
# significativo e le chain europee non sono su Yahoo.
UNDERLYING_MAP: dict[str, dict] = {
    # --- DAX (proxy USA EWG, unica via gratis) ---
    "^GDAXI": {"proxy": "EWG",  "label": "EWG → DAX (correlazione ~0.95)"},

    # --- ETF USA con chain diretta su Yahoo (no proxy) ---
    "EWG":    {"proxy": "EWG",  "label": "chain CBOE diretta"},
    "GLD":    {"proxy": "GLD",  "label": "chain CBOE diretta"},
    "GDX":    {"proxy": "GDX",  "label": "chain CBOE diretta"},
    "SLV":    {"proxy": "SLV",  "label": "chain CBOE diretta"},
    "USO":    {"proxy": "USO",  "label": "chain CBOE diretta"},
    "EEM":    {"proxy": "EEM",  "label": "chain CBOE diretta"},

    # --- ETF globali listati in EU → proxy USA equivalente ---
    "VWCE.DE": {"proxy": "VT",   "label": "VT → VWCE FTSE All-World (correlazione ~0.99)"},
    "IWDA.AS": {"proxy": "URTH", "label": "URTH → IWDA MSCI World (correlazione ~0.99)"},

    # --- Future commodity → ETF equivalente ---
    "GC=F":   {"proxy": "GLD",  "label": "GLD → Gold futures (correlazione ~0.99)"},
}

# Risk-free rate annualizzato (USD). Gamma è poco sensibile a r,
# 4% è una buona approssimazione 2024-2026.
RISK_FREE_RATE = 0.04

# Quante scadenze prossime considerare. Front-month + next-month catturano
# la maggior parte dell'OI e del gamma rilevante per il dealer hedging.
MAX_EXPIRIES = 2

# Finestra strike attorno allo spot del proxy (±%)
STRIKE_WINDOW_PCT = 0.20

# Cache TTL: l'OI si aggiorna a fine giornata, basta un refresh giornaliero
CACHE_TTL_SECONDS = 6 * 3600


# ─── DATA MODEL ──────────────────────────────────────────────────────────────

@dataclass
class GexLevels:
    available: bool
    ticker: str
    spot: float | None = None
    call_wall: float | None = None
    put_wall: float | None = None
    proxy: str | None = None
    note: str | None = None
    expiries_used: list[str] | None = None
    strikes_used: int = 0
    last_update: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


# ─── STATE ────────────────────────────────────────────────────────────────────

_cache: dict[str, GexLevels] = {}
_cache_ts: dict[str, float] = {}
_lock = threading.Lock()


# ─── BLACK-SCHOLES GAMMA ─────────────────────────────────────────────────────

def _gamma_bs(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Gamma BS per call=put. T in anni, sigma in decimale (0.25 = 25%)."""
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + sigma * sigma / 2.0) * T) / (sigma * math.sqrt(T))
    npd1 = math.exp(-d1 * d1 / 2.0) / math.sqrt(2.0 * math.pi)
    return npd1 / (S * sigma * math.sqrt(T))


# ─── CORE ────────────────────────────────────────────────────────────────────

def _get_spot(ticker: str) -> float | None:
    try:
        hist = yf.Ticker(ticker).history(period="5d", interval="1d", auto_adjust=True)
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception:
        return None


def _years_to_expiry(expiry_str: str) -> float:
    """yfinance espone le scadenze come 'YYYY-MM-DD'."""
    try:
        d = datetime.strptime(expiry_str, "%Y-%m-%d")
    except ValueError:
        return 0.0
    delta = (d - datetime.now()).total_seconds() / 86400.0
    return max(delta / 365.25, 1.0 / 365.25)


def _compute(ticker_yahoo: str) -> GexLevels:
    cfg = UNDERLYING_MAP[ticker_yahoo]
    proxy = cfg["proxy"]

    # Spot reali per ticker richiesto + proxy
    spot_main  = _get_spot(ticker_yahoo)
    spot_proxy = _get_spot(proxy) if proxy != ticker_yahoo else spot_main
    if not spot_main or not spot_proxy:
        return GexLevels(False, ticker_yahoo, reason="spot non disponibile")

    # Chain del proxy
    try:
        tk = yf.Ticker(proxy)
        expiries = list(tk.options)[:MAX_EXPIRIES]
    except Exception as e:
        return GexLevels(False, ticker_yahoo, reason=f"yfinance chain error: {e}")

    if not expiries:
        return GexLevels(False, ticker_yahoo, reason=f"nessuna chain per {proxy}")

    lo, hi = spot_proxy * (1 - STRIKE_WINDOW_PCT), spot_proxy * (1 + STRIKE_WINDOW_PCT)
    multiplier = 100.0  # ETF/azioni USA = 100 azioni per contratto

    gex_by_strike: dict[float, float] = {}

    for expiry in expiries:
        try:
            chain = tk.option_chain(expiry)
        except Exception:
            continue
        T = _years_to_expiry(expiry)

        for df, sign in ((chain.calls, +1.0), (chain.puts, -1.0)):
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                K = float(row.get("strike", 0) or 0)
                if not (lo <= K <= hi):
                    continue
                oi = row.get("openInterest", 0)
                iv = row.get("impliedVolatility", 0)
                if pd.isna(oi) or pd.isna(iv) or oi <= 0 or iv <= 0:
                    continue
                gamma = _gamma_bs(spot_proxy, K, T, RISK_FREE_RATE, float(iv))
                if gamma <= 0:
                    continue
                # GEX in unità monetarie del proxy (USD per EWG)
                contrib = sign * gamma * float(oi) * multiplier * (spot_proxy ** 2)
                gex_by_strike[K] = gex_by_strike.get(K, 0.0) + contrib

    if len(gex_by_strike) < 3:
        return GexLevels(False, ticker_yahoo, reason="OI/IV insufficienti per il calcolo")

    # Call Wall: strike con max GEX positivo (i MM hanno tanto gamma positivo = vendono ribassi, comprano rialzi → resistenza)
    # Put Wall:  strike con min GEX (più negativo) (gamma negativo = supporto)
    call_wall_proxy = max(gex_by_strike, key=lambda k: gex_by_strike[k])
    put_wall_proxy  = min(gex_by_strike, key=lambda k: gex_by_strike[k])
    if gex_by_strike[call_wall_proxy] <= 0:
        call_wall_proxy = None
    if gex_by_strike[put_wall_proxy] >= 0:
        put_wall_proxy = None

    # Riproiezione: livelli del proxy → scala del ticker richiesto
    scale = spot_main / spot_proxy if proxy != ticker_yahoo else 1.0

    return GexLevels(
        available=True,
        ticker=ticker_yahoo,
        spot=round(spot_main, 2),
        call_wall=round(call_wall_proxy * scale, 2) if call_wall_proxy else None,
        put_wall=round(put_wall_proxy * scale, 2)  if put_wall_proxy  else None,
        proxy=proxy,
        note=cfg.get("label"),
        expiries_used=expiries,
        strikes_used=len(gex_by_strike),
        last_update=datetime.now().isoformat(timespec="seconds"),
    )


# ─── PUBLIC API ──────────────────────────────────────────────────────────────

def is_supported(ticker_yahoo: str) -> bool:
    return ticker_yahoo in UNDERLYING_MAP


def get_gex(ticker_yahoo: str, force_refresh: bool = False) -> dict:
    if not is_supported(ticker_yahoo):
        return GexLevels(False, ticker_yahoo,
                         reason="ticker non supportato").to_dict()

    now = time.time()
    with _lock:
        cached = _cache.get(ticker_yahoo)
        ts = _cache_ts.get(ticker_yahoo, 0)
        if cached and not force_refresh and (now - ts) < CACHE_TTL_SECONDS:
            return cached.to_dict()

    try:
        result = _compute(ticker_yahoo)
    except Exception as e:
        result = GexLevels(False, ticker_yahoo, reason=f"compute error: {e}")

    with _lock:
        _cache[ticker_yahoo] = result
        _cache_ts[ticker_yahoo] = now

    return result.to_dict()


def refresh_all_supported() -> dict[str, dict]:
    return {t: get_gex(t, force_refresh=True) for t in UNDERLYING_MAP}
