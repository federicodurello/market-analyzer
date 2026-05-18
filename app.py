from flask import Flask, jsonify, render_template, request
from analyzer import analyze_all, get_chart_data
from assets import ASSETS
from backtest import backtest_all as _backtest_all
import gex as gex_mod
import threading
import time
from datetime import datetime, timedelta

app = Flask(__name__)
PERIODS = ["6mo", "1y", "2y"]
DEFAULT_PERIOD = "2y"

# Refresh automatico dei dati ogni REFRESH_SECONDS.
# Nota: i dati di mercato gratuiti (Yahoo) sono comunque ritardati di ~15 min,
# quindi refresh piu' frequenti non darebbero dati piu' "freschi" — solo piu' richieste.
REFRESH_SECONDS  = 90
BACKTEST_SECONDS = 1800   # il backtest 3y e' pesante: si rilancia ogni 30 min

_cache      = {"data": {}, "last_update": None, "next_update": None, "loading": True}
_cache_lock = threading.Lock()
_ready      = threading.Event()

_bt_cache = {"data": {}, "ready": False}
_bt_lock  = threading.Lock()


def _do_refresh():
    """Ricarica DEFAULT_PERIOD + ogni periodo gia' richiesto, cosi' tutte le viste restano fresche."""
    with _cache_lock:
        _cache["loading"] = True
        periods = set(_cache["data"].keys()) | {DEFAULT_PERIOD}
    for period in periods:
        results = analyze_all(ASSETS, period)
        with _cache_lock:
            _cache["data"][period] = results
    next_upd = datetime.now() + timedelta(seconds=REFRESH_SECONDS)
    with _cache_lock:
        _cache["last_update"] = datetime.now().isoformat()
        _cache["next_update"] = next_upd.isoformat()
        _cache["loading"]     = False
    _ready.set()


def _run_backtest():
    with _bt_lock:
        _bt_cache["ready"] = False
    results = _backtest_all(ASSETS)
    with _bt_lock:
        _bt_cache["data"]  = results
        _bt_cache["ready"] = True


def _bg_loop():
    _do_refresh()
    threading.Thread(target=_run_backtest, daemon=True).start()
    last_bt = time.time()
    while True:
        time.sleep(REFRESH_SECONDS)
        _do_refresh()
        if time.time() - last_bt >= BACKTEST_SECONDS:
            threading.Thread(target=_run_backtest, daemon=True).start()
            last_bt = time.time()


threading.Thread(target=_bg_loop, daemon=True).start()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chart/<path:ticker>")
def chart_window(ticker):
    """Pagina dedicata full-screen per il grafico di un ticker."""
    return render_template("chart.html", ticker=ticker)


@app.route("/api/status")
def api_status():
    with _cache_lock:
        return jsonify({
            "loading":     _cache["loading"],
            "last_update": _cache["last_update"],
            "next_update": _cache["next_update"],
            "ready":       _ready.is_set(),
        })


@app.route("/api/analyze")
def api_analyze():
    period   = request.args.get("period", DEFAULT_PERIOD)
    if period not in PERIODS:
        period = DEFAULT_PERIOD
    category = request.args.get("category", "all")

    _ready.wait(timeout=180)

    with _cache_lock:
        if period in _cache["data"]:
            results = list(_cache["data"][period])
        else:
            results = analyze_all(ASSETS, period)
            _cache["data"][period] = results

    if category != "all":
        results = [r for r in results if r["category"] == category]

    return jsonify(results)


@app.route("/api/chart/<path:ticker>")
def api_chart(ticker):
    period = request.args.get("period", DEFAULT_PERIOD)
    if period not in PERIODS:
        period = DEFAULT_PERIOD
    return jsonify(get_chart_data(ticker, period))


@app.route("/api/categories")
def api_categories():
    cats = sorted({a["category"] for a in ASSETS})
    return jsonify(["all"] + cats)


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    threading.Thread(target=_do_refresh, daemon=True).start()
    return jsonify({"status": "refreshing"})


@app.route("/api/backtest")
def api_backtest():
    with _bt_lock:
        return jsonify({
            "ready": _bt_cache["ready"],
            "data":  _bt_cache["data"],
        })


@app.route("/api/backtest/<path:ticker>")
def api_backtest_ticker(ticker):
    with _bt_lock:
        return jsonify({
            "ready": _bt_cache["ready"],
            "data":  _bt_cache["data"].get(ticker),
        })


@app.route("/api/gex/<path:ticker>")
def api_gex(ticker):
    """Gamma Exposure (Zero Gamma / Call Wall / Put Wall) via IBKR TWS.
    Solo per i ticker mappati in gex.UNDERLYING_MAP."""
    if not gex_mod.is_supported(ticker):
        return jsonify({"available": False, "ticker": ticker,
                        "reason": "ticker non supportato"})
    force = request.args.get("refresh") == "1"
    return jsonify(gex_mod.get_gex(ticker, force_refresh=force))


@app.route("/api/gex/refresh", methods=["POST"])
def api_gex_refresh():
    threading.Thread(target=gex_mod.refresh_all_supported, daemon=True).start()
    return jsonify({"status": "refreshing"})


if __name__ == "__main__":
    print("\n  Market Analyzer -> http://127.0.0.1:5000\n")
    app.run(debug=False, port=5000, threaded=True)
