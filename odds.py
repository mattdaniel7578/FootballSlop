"""
Spread data source for games.

For now, spreads are entered manually by an admin via the "Add game" form
(see routes in main.py / templates/admin_add_game.html), because DraftKings
has no public API of its own.

TODO: replace manual entry with a live odds API integration, e.g.
https://the-odds-api.com/ (free tier available). That API returns a list of
bookmakers per game, including "draftkings", each with a "spreads" market.
A rough sketch of what that integration would look like:

    import requests

    def fetch_draftkings_spread(api_key, home_team, away_team):
        resp = requests.get(
            "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds",
            params={
                "apiKey": api_key,
                "regions": "us",
                "markets": "spreads",
                "bookmakers": "draftkings",
            },
            timeout=10,
        )
        resp.raise_for_status()
        for event in resp.json():
            if {event["home_team"], event["away_team"]} == {home_team, away_team}:
                dk = next(
                    (b for b in event["bookmakers"] if b["key"] == "draftkings"),
                    None,
                )
                if dk:
                    outcomes = dk["markets"][0]["outcomes"]
                    favorite = min(outcomes, key=lambda o: o["point"])
                    return favorite["name"], abs(favorite["point"])
        return None

This module intentionally does not call any external service yet.
"""
