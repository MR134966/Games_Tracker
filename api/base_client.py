import requests

class GameDataFetcher:
    def __init__(self):
        self.base_url = "https://www.cheapshark.com/api/1.0"
        self.store_mapping = {
            "1": "Steam",
            "11": "GOG",
            "25": "Epic Games"
        }

    def search_deals(self, game_name):
        url = f"{self.base_url}/deals"
        params = {"title": game_name}
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException:
            return None

    def get_usd_to_pln_rate(self):
        url = "http://api.nbp.pl/api/exchangerates/rates/a/usd/?format=json"
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.json()['rates'][0]['mid']
        except requests.exceptions.RequestException:
            return 4.0

    def get_game_by_id(self, game_id):
        url = f"{self.base_url}/games"
        params = {"id": game_id}
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException:
            return None

    def get_games_by_ids(self, game_ids):
        if not game_ids:
            return {}
        url = f"{self.base_url}/games"
        params = {"ids": ",".join(game_ids)}
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException:
            return {}

    def get_hot_deals(self):
        url = f"{self.base_url}/deals"
        params = {"sortBy": "Deal Rating", "onSale": 1, "storeID": "1,11,25"}
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException:
            return None