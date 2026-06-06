from flask import Flask, render_template, request, redirect, url_for, jsonify
from api.base_client import GameDataFetcher
import json
import sqlite3

app = Flask(__name__)
api_fetcher = GameDataFetcher()


def init_db():
    conn = sqlite3.connect('tracker.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS watchlist
                 (
                     game_id
                     TEXT
                     PRIMARY
                     KEY,
                     title
                     TEXT
                 )''')
    conn.commit()
    conn.close()


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
                            "savings": round(savings, 0)
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
                           chart_data=chart_data, best_deal_title=best_deal_title, exchange_rate=exchange_rate)


@app.route("/api/historical_low/<game_id>")
def historical_low(game_id):
    game_details = api_fetcher.get_game_by_id(game_id)
    if game_details and "cheapestPriceEver" in game_details:
        return jsonify({"price_usd": float(game_details["cheapestPriceEver"].get("price", 0))})
    return jsonify({"price_usd": None})


@app.route("/track", methods=["POST"])
def track_game():
    game_id = request.form.get("game_id")
    title = request.form.get("title")

    if game_id and title:
        conn = sqlite3.connect('tracker.db')
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO watchlist (game_id, title) VALUES (?, ?)", (game_id, title))
        conn.commit()
        conn.close()

    return redirect(url_for('watchlist'))


@app.route("/untrack", methods=["POST"])
def untrack_game():
    game_id = request.form.get("game_id")

    if game_id:
        conn = sqlite3.connect('tracker.db')
        c = conn.cursor()
        c.execute("DELETE FROM watchlist WHERE game_id = ?", (game_id,))
        conn.commit()
        conn.close()

    return redirect(url_for('watchlist'))


@app.route("/watchlist")
def watchlist():
    conn = sqlite3.connect('tracker.db')
    c = conn.cursor()
    c.execute("SELECT game_id, title FROM watchlist")
    tracked_games = c.fetchall()
    conn.close()

    exchange_rate = api_fetcher.get_usd_to_pln_rate()
    live_tracked_data = []

    for game_id, title in tracked_games:
        game_info = api_fetcher.get_game_by_id(game_id)
        if game_info and "deals" in game_info and len(game_info["deals"]) > 0:
            best_deal = game_info["deals"][0]
            price_pln = float(best_deal.get("price", 0)) * exchange_rate
            normal_pln = float(best_deal.get("retailPrice", 0)) * exchange_rate
            savings = float(best_deal.get("savings", 0))
            store_name = api_fetcher.store_mapping.get(best_deal.get("storeID"), "Inny sklep")

            live_tracked_data.append({
                "game_id": game_id,
                "title": title,
                "price_pln": round(price_pln, 2),
                "normal_pln": round(normal_pln, 2),
                "savings": round(savings, 0),
                "store_name": store_name
            })

    return render_template("watchlist.html", tracked_data=live_tracked_data, exchange_rate=exchange_rate)


@app.route("/top_deals")
def top_deals():
    exchange_rate = api_fetcher.get_usd_to_pln_rate()
    raw_deals = api_fetcher.get_hot_deals()
    hot_deals = []
    seen_titles = set()

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
                "metacritic": metacritic
            })

            if len(hot_deals) >= 12:
                break

    return render_template("top_deals.html", deals=hot_deals)


if __name__ == "__main__":
    app.run(debug=True, port=5000)