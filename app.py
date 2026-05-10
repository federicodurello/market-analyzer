from flask import Flask, jsonify, render_template, request
from analyzer import analyze_all, get_chart_data
from assets import ASSETS

app = Flask(__name__)

PERIODS = ["1mo", "3mo", "6mo", "1y", "2y"]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analyze")
def api_analyze():
    period = request.args.get("period", "6mo")
    if period not in PERIODS:
        period = "6mo"
    category = request.args.get("category", "all")

    assets = ASSETS
    if category != "all":
        assets = [a for a in ASSETS if a["category"] == category]

    results = analyze_all(assets, period)
    return jsonify(results)


@app.route("/api/chart/<path:ticker>")
def api_chart(ticker):
    period = request.args.get("period", "6mo")
    if period not in PERIODS:
        period = "6mo"
    data = get_chart_data(ticker, period)
    return jsonify(data)


@app.route("/api/categories")
def api_categories():
    cats = sorted(set(a["category"] for a in ASSETS))
    return jsonify(["all"] + cats)


if __name__ == "__main__":
    print("\n  Market Analyzer avviato → http://127.0.0.1:5000\n")
    app.run(debug=False, port=5000)
