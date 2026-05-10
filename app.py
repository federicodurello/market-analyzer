from flask import Flask, jsonify, render_template, request
from analyzer import analyze_all, get_chart_data
from assets import ASSETS
from backtest import backtest_all as _backtest_all
import threading
import time
from datetime import datetime, timedelta

app = Flask(__name__)
PERIODS = ["1mo", "3mo", "6mo", "1y", "2y"]
DEFAULT_PERIOD = "2y"

_cache      = {"data": {}, "last_update": None, "next_update": None, "loading": True}
_cache_lock = threading.Lock()
_ready      = threading.Event()

_bt_cache = {"data": {}, "ready": False}
_bt_lock  = threading.Lock()


def _next_monday_9am() -> datetime:
    now = datetime.now()
    weekday = now.weekday()  # 0=Mon, 6=Sun
    if weekday == 0:
        nine_am = now.replace(hour=9, minute=0, second=0, microsecond=0)
        days_ahead = 0 if now < nine_am else 7
    else:
        days_ahead = (7 - weekday) % 7
    target = (now + timedelta(days=days_ahead)).replace(hour=9, minute=0, second=0, microsecond=0)
    return target


def _do_refresh(period: str = DEFAULT_PERIOD):
    with _cache_lock:
        _cache["loading"] = True
    results  = analyze_all(ASSETS, period)
    next_upd = _next_monday_9am()
    with _cache_lock:
        _cache["data"][period] = results
        _cache["last_update"]  = datetime.now().isoformat()
        _cache["next_update"]  = next_upd.isoformat()
        _cache["loading"]      = False
    _ready.set()


def _run_backtest():
    with _bt_lock:
        _bt_cache["ready"] = False
    results = _backtest_all(ASSETS)
    with _bt_lock:
        _bt_cache["data"]  = results
        _bt_cache["ready"] = True


def _bg_loop():
    _do_refresh(DEFAULT_PERIOD)
    threading.Thread(target=_run_backtest, daemon=True).start()
    while True:
        next_mon = _next_monday_9am()
        wait = (next_mon - datetime.now()).total_seconds()
        if wait > 0:
            time.sleep(wait)
        _do_refresh(DEFAULT_PERIOD)
        threading.Thread(target=_run_backtest, daemon=True).start()


threading.Thread(target=_bg_loop, daemon=True).start()


@app.route("/")
def index():
    return render_template("index.html")


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
    period = request.args.get("period", DEFAULT_PERIOD)
    threading.Thread(target=_do_refresh, args=(period,), daemon=True).start()
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


if __name__ == "__main__":
    print("\n  Market Analyzer -> http://127.0.0.1:5000\n")
    app.run(debug=False, port=5000, threaded=True)
