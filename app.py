from flask import Flask, jsonify, render_template, request
from analyzer import analyze_all, get_chart_data
from assets import ASSETS
import threading
import time
from datetime import datetime

app = Flask(__name__)
PERIODS = ["1mo", "3mo", "6mo", "1y", "2y"]

_cache      = {"data": {}, "last_update": None, "loading": True}
_cache_lock = threading.Lock()
_ready      = threading.Event()


def _do_refresh(period: str = "6mo"):
    with _cache_lock:
        _cache["loading"] = True
    results = analyze_all(ASSETS, period)
    with _cache_lock:
        _cache["data"][period] = results
        _cache["last_update"]  = datetime.now().isoformat()
        _cache["loading"]      = False
    _ready.set()


def _bg_loop():
    while True:
        _do_refresh("6mo")
        time.sleep(300)  # refresh every 5 minutes


# Start background download immediately on startup
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
            "ready":       _ready.is_set(),
        })


@app.route("/api/analyze")
def api_analyze():
    period   = request.args.get("period", "6mo")
    if period not in PERIODS:
        period = "6mo"
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
    period = request.args.get("period", "6mo")
    if period not in PERIODS:
        period = "6mo"
    return jsonify(get_chart_data(ticker, period))


@app.route("/api/categories")
def api_categories():
    cats = sorted({a["category"] for a in ASSETS})
    return jsonify(["all"] + cats)


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    period = request.args.get("period", "6mo")
    threading.Thread(target=_do_refresh, args=(period,), daemon=True).start()
    return jsonify({"status": "refreshing"})


if __name__ == "__main__":
    print("\n  Market Analyzer → http://127.0.0.1:5000\n")
    app.run(debug=False, port=5000, threaded=True)
