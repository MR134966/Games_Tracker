from flask import Flask, render_template, request, jsonify
from api.base_client import GameDataFetcher
import json
import sqlite3

app = Flask(__name__)
api_fetcher = GameDataFetcher()


def init_db():
    with sqlite3.connect('tracker.db') as conn:
        c = conn.cursor()
        c.execute("PRAGMA foreign_keys = ON")
        c.execute('''CREATE TABLE IF NOT EXISTS watchlist
                     (
                         game_id TEXT PRIMARY KEY,
                         title TEXT
                     )''')
        c.execute('''CREATE TABLE IF NOT EXISTS price_history
                     (
                         id INTEGER PRIMARY KEY AUTOINCREMENT,
                         game_id TEXT,
                         price_pln REAL,
                         checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                         FOREIGN KEY(game_id) REFERENCES watchlist(game_id) ON DELETE CASCADE
                     )''')


init_db()


@app.route("/", methods=["GET", "POST"])
def index():
    deals = None
    error = None
    search_query = ""
    chart_labels = "[]"
    chart_data = "[]"
    best_deal_title = ""
    exchange_rate = api_fetcher.get_usd_to_pln_rate()

    tracked_ids = []
    try:
        with sqlite3.connect('tracker.db') as conn:
            c = conn.cursor()
            c.execute("SELECT game_id FROM watchlist")
            tracked_ids = [row[0] for row in c.fetchall()]
    except Exception:
        pass

    if request.method == "POST":
        search_query = request.form.get("game_name", "").strip()
        sort_by = request.form.get("sort_by", "najniższa")
        allowed_stores = request.form.getlist("store")

        if not search_query:
            error = "Najpierw wpisz nazwę gry!"
        else:
            raw_deals = api_fetcher.search_deals(search_query)

            if raw_deals is None:
                error = "Błąd połączenia z API."
            elif len(raw_deals) == 0:
                error = "Nie znaleziono ofert spełniających kryteria."
            else:
                deals = []
                for deal in raw_deals:
                    store_id = deal.get("storeID")
                    if store_id in allowed_stores:
                        price_pln = float(deal.get("salePrice", 0)) * exchange_rate
                        normal_pln = float(deal.get("normalPrice", 0)) * exchange_rate
                        savings = float(deal.get("savings", 0))
                        store_name = api_fetcher.store_mapping.get(store_id, "Inny sklep")

                        deals.append({
                            "game_id": deal.get("gameID"),
                            "title": deal.get("title"),
                            "store_name": store_name,
                            "price_pln": round(price_pln, 2),
                            "normal_pln": round(normal_pln, 2),
                            "savings": round(savings, 0),
                            "thumb": deal.get("thumb")
                        })

                if sort_by == "najniższa":
                    deals.sort(key=lambda x: x["price_pln"])
                elif sort_by == "najwyższa":
                    deals.sort(key=lambda x: x["price_pln"], reverse=True)
                elif sort_by == "obniżka":
                    deals.sort(key=lambda x: x["savings"], reverse=True)

                if deals:
                    best_deal = deals[0]
                    best_deal_title = best_deal["title"]
                    current_price = best_deal["price_pln"]
                    normal_price = best_deal["normal_pln"]

                    game_details = api_fetcher.get_game_by_id(best_deal["game_id"])

                    if game_details and "cheapestPriceEver" in game_details:
                        cheapest_usd = float(game_details["cheapestPriceEver"].get("price", 0))
                        cheapest_pln = round(cheapest_usd * exchange_rate, 2)
                        cheapest_pln = min(cheapest_pln, current_price)
                    else:
                        cheapest_pln = current_price

                    chart_labels = json.dumps(["Cena Standardowa", "Obecna Oferta", "Historyczne Minimum"])
                    chart_data = json.dumps([normal_price, current_price, cheapest_pln])

    return render_template("index.html", deals=deals, error=error, search_query=search_query, chart_labels=chart_labels,
                           chart_data=chart_data, best_deal_title=best_deal_title, exchange_rate=exchange_rate,
                           tracked_ids=tracked_ids)


@app.route("/api/historical_low/<game_id>")
def historical_low(game_id):
    game_details = api_fetcher.get_game_by_id(game_id)
    if game_details and "cheapestPriceEver" in game_details:
        return jsonify({"price_usd": float(game_details["cheapestPriceEver"].get("price", 0))})
    return jsonify({"price_usd": None})


@app.route("/track", methods=["POST"])
def track_game():
    if request.is_json:
        data = request.get_json()
        game_id = data.get("game_id")
        title = data.get("title")
        price_pln = data.get("price_pln")
    else:
        game_id = request.form.get("game_id")
        title = request.form.get("title")
        price_pln = request.form.get("price_pln")

    if game_id and title:
        try:
            with sqlite3.connect('tracker.db') as conn:
                c = conn.cursor()
                c.execute("PRAGMA foreign_keys = ON")
                c.execute("INSERT OR IGNORE INTO watchlist (game_id, title) VALUES (?, ?)", (game_id, title))
                if price_pln is not None:
                    c.execute("INSERT INTO price_history (game_id, price_pln) VALUES (?, ?)", (game_id, float(price_pln)))
            return jsonify({"success": True, "message": "Gra dodana do obserwowanych.", "action": "track", "game_id": game_id})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    return jsonify({"success": False, "error": "Brak game_id lub title"}), 400


@app.route("/untrack", methods=["POST"])
def untrack_game():
    if request.is_json:
        data = request.get_json()
        game_id = data.get("game_id")
    else:
        game_id = request.form.get("game_id")

    if game_id:
        try:
            with sqlite3.connect('tracker.db') as conn:
                c = conn.cursor()
                c.execute("PRAGMA foreign_keys = ON")
                c.execute("DELETE FROM watchlist WHERE game_id = ?", (game_id,))
            return jsonify({"success": True, "message": "Gra usunięta z obserwowanych.", "action": "untrack", "game_id": game_id})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    return jsonify({"success": False, "error": "Brak game_id"}), 400


@app.route("/watchlist")
def watchlist():
    tracked_games = []
    tracked_prices = {}
    try:
        with sqlite3.connect('tracker.db') as conn:
            c = conn.cursor()
            c.execute("SELECT game_id, title FROM watchlist")
            tracked_games = c.fetchall()
            for game_id, _ in tracked_games:
                c.execute("SELECT price_pln FROM price_history WHERE game_id = ? ORDER BY checked_at ASC LIMIT 1", (game_id,))
                row = c.fetchone()
                if row:
                    tracked_prices[game_id] = row[0]
    except Exception:
        pass

    exchange_rate = api_fetcher.get_usd_to_pln_rate()
    live_tracked_data = []

    if tracked_games:
        game_ids = [game[0] for game in tracked_games]
        games_info = api_fetcher.get_games_by_ids(game_ids)

        for game_id, title in tracked_games:
            game_info = games_info.get(game_id)
            if game_info and "deals" in game_info and len(game_info["deals"]) > 0:
                best_deal = game_info["deals"][0]
                price_pln = float(best_deal.get("price", 0)) * exchange_rate
                normal_pln = float(best_deal.get("retailPrice", 0)) * exchange_rate
                savings = float(best_deal.get("savings", 0))
                store_name = api_fetcher.store_mapping.get(best_deal.get("storeID"), "Inny sklep")
                thumb = game_info.get("info", {}).get("thumb", "")

                tracked_price = tracked_prices.get(game_id, price_pln)
                price_diff = round(price_pln - tracked_price, 2)

                live_tracked_data.append({
                    "game_id": game_id,
                    "title": title,
                    "price_pln": round(price_pln, 2),
                    "normal_pln": round(normal_pln, 2),
                    "savings": round(savings, 0),
                    "store_name": store_name,
                    "thumb": thumb,
                    "price_diff": price_diff
                })

    stats = {
        "total_normal": 0.0,
        "total_current": 0.0,
        "total_savings_pln": 0.0,
        "avg_savings_pct": 0,
        "biggest_deal_title": "Brak",
        "biggest_deal_pct": 0
    }

    if live_tracked_data:
        stats["total_normal"] = round(sum(g["normal_pln"] for g in live_tracked_data), 2)
        stats["total_current"] = round(sum(g["price_pln"] for g in live_tracked_data), 2)
        stats["total_savings_pln"] = round(stats["total_normal"] - stats["total_current"], 2)
        
        savings_list = [g["savings"] for g in live_tracked_data]
        stats["avg_savings_pct"] = round(sum(savings_list) / len(savings_list)) if savings_list else 0
        
        biggest = max(live_tracked_data, key=lambda x: x["savings"])
        if biggest["savings"] > 0:
            stats["biggest_deal_title"] = biggest["title"]
            stats["biggest_deal_pct"] = biggest["savings"]

    return render_template("watchlist.html", tracked_data=live_tracked_data, exchange_rate=exchange_rate, stats=stats)


@app.route("/top_deals")
def top_deals():
    exchange_rate = api_fetcher.get_usd_to_pln_rate()
    raw_deals = api_fetcher.get_hot_deals()
    hot_deals = []
    seen_titles = set()

    tracked_ids = []
    try:
        with sqlite3.connect('tracker.db') as conn:
            c = conn.cursor()
            c.execute("SELECT game_id FROM watchlist")
            tracked_ids = [row[0] for row in c.fetchall()]
    except Exception:
        pass

    if raw_deals:
        for deal in raw_deals:
            title = deal.get("title")
            if title in seen_titles:
                continue
            seen_titles.add(title)

            price_pln = float(deal.get("salePrice", 0)) * exchange_rate
            normal_pln = float(deal.get("normalPrice", 0)) * exchange_rate
            savings = float(deal.get("savings", 0))
            store_name = api_fetcher.store_mapping.get(deal.get("storeID"), "Inny sklep")
            metacritic = deal.get("metacriticScore", "Brak")

            hot_deals.append({
                "game_id": deal.get("gameID"),
                "title": title,
                "store_name": store_name,
                "price_pln": round(price_pln, 2),
                "normal_pln": round(normal_pln, 2),
                "savings": round(savings, 0),
                "metacritic": metacritic,
                "thumb": deal.get("thumb")
            })

            if len(hot_deals) >= 12:
                break

    return render_template("top_deals.html", deals=hot_deals, tracked_ids=tracked_ids)


if __name__ == "__main__":
    app.run(debug=True, port=5000)