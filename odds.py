"""
Automatic DraftKings spread + result sync via https://the-odds-api.com/
(free tier available). Runs on a schedule from app.py — see
_start_odds_scheduler() — so games and results need no manual entry.

Requires ODDS_API_KEY in the environment; sync_all() is a no-op (logged)
when it's unset, so the app still runs without it, just with no games.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from extensions import db
from models import Game, classify_slate, compute_snap_at, now_eastern

logger = logging.getLogger(__name__)

EASTERN = ZoneInfo("America/New_York")

ODDS_URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"
SCORES_URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/scores"

# Public, no-key-required — the-odds-api doesn't include venue data, but
# this does, including neutral-site/international games (e.g. London,
# Melbourne) that a simple "home team's own stadium" guess gets wrong.
ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"


def _to_eastern_naive(iso_utc):
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    return dt.astimezone(EASTERN).replace(tzinfo=None)


def _season_and_week(kickoff_et, season_start_date):
    if season_start_date is not None:
        week = max(1, (kickoff_et.date() - season_start_date).days // 7 + 1)
        return season_start_date.year, week
    # No anchor configured: best-effort season year, week always 1.
    season = kickoff_et.year if kickoff_et.month >= 3 else kickoff_et.year - 1
    return season, 1


def sync_spreads(app):
    api_key = app.config["ODDS_API_KEY"]
    if not api_key:
        logger.info("ODDS_API_KEY not set; skipping DraftKings spread sync.")
        return

    resp = requests.get(
        ODDS_URL,
        params={
            "apiKey": api_key,
            "regions": "us",
            "markets": "spreads",
            "bookmakers": "draftkings",
            "dateFormat": "iso",
        },
        timeout=15,
    )
    resp.raise_for_status()

    season_start_date = app.config["SEASON_START_DATE"]
    now = now_eastern()

    for event in resp.json():
        dk = next((b for b in event.get("bookmakers", []) if b["key"] == "draftkings"), None)
        if not dk:
            continue
        market = next((m for m in dk["markets"] if m["key"] == "spreads"), None)
        if not market or len(market.get("outcomes", [])) != 2:
            continue

        outcomes = market["outcomes"]
        favorite = min(outcomes, key=lambda o: o["point"])
        favorite_team = favorite["name"]
        spread_points = abs(favorite["point"])

        kickoff_et = _to_eastern_naive(event["commence_time"])
        season, week = _season_and_week(kickoff_et, season_start_date)
        slate = classify_slate(kickoff_et)
        snap_at = compute_snap_at(kickoff_et)

        game = Game.query.filter_by(external_id=event["id"]).first()
        if game is None:
            db.session.add(
                Game(
                    external_id=event["id"],
                    season=season,
                    week=week,
                    slate=slate,
                    home_team=event["home_team"],
                    away_team=event["away_team"],
                    favorite_team=favorite_team,
                    spread_points=spread_points,
                    kickoff_at=kickoff_et,
                    line_snapshot_at=now if now >= snap_at else None,
                )
            )
        elif game.line_snapshot_at is None and not game.is_locked():
            # The line stays live until its snap deadline (see
            # compute_snap_at) — once we're past it, this same sync tick
            # records the final line and every later tick leaves it alone.
            game.favorite_team = favorite_team
            game.spread_points = spread_points
            game.kickoff_at = kickoff_et
            game.slate = slate
            if now >= snap_at:
                game.line_snapshot_at = now

    db.session.commit()


def sync_results(app):
    api_key = app.config["ODDS_API_KEY"]
    if not api_key:
        return

    resp = requests.get(
        SCORES_URL,
        params={"apiKey": api_key, "daysFrom": 3, "dateFormat": "iso"},
        timeout=15,
    )
    resp.raise_for_status()

    for event in resp.json():
        if not event.get("completed") or not event.get("scores"):
            continue

        game = Game.query.filter_by(external_id=event["id"]).first()
        if game is None or game.winner is not None:
            continue

        scores = {s["name"]: int(s["score"]) for s in event["scores"]}
        if game.home_team not in scores or game.away_team not in scores:
            continue

        underdog_team = game.underdog_team()
        margin = scores[game.favorite_team] - scores[underdog_team] - game.spread_points

        if margin > 0:
            game.winner = game.favorite_team
        elif margin < 0:
            game.winner = underdog_team
        else:
            game.winner = "PUSH"

    db.session.commit()


def fetch_espn_venues(season, week):
    """{(home_team, away_team): "Venue Name"} for one week, using ESPN's own
    team display names (which match the-odds-api's) — just the stadium
    name, since that alone is enough to flag a neutral-site/international
    game without the extra city/state text."""
    resp = requests.get(
        ESPN_SCOREBOARD_URL,
        params={"seasontype": 2, "week": week, "year": season},
        timeout=15,
    )
    resp.raise_for_status()

    venues = {}
    for event in resp.json().get("events", []):
        comp = event["competitions"][0]
        venue = comp.get("venue") or {}
        name = venue.get("fullName")
        if not name:
            continue

        competitors = comp.get("competitors", [])
        home = next((c["team"]["displayName"] for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c["team"]["displayName"] for c in competitors if c.get("homeAway") == "away"), None)
        if home and away:
            venues[(home, away)] = name

    return venues


def sync_venues(app):
    weeks = db.session.query(Game.season, Game.week).distinct().all()
    for season, week in weeks:
        try:
            venues = fetch_espn_venues(season, week)
        except Exception:
            logger.exception("ESPN venue sync failed for season=%s week=%s", season, week)
            continue

        games = Game.query.filter_by(season=season, week=week).all()
        for game in games:
            location = venues.get((game.home_team, game.away_team))
            if location:
                game.location = location

    db.session.commit()


def sync_all(app):
    """Entry point for the scheduled job in app.py."""
    with app.app_context():
        try:
            sync_spreads(app)
        except Exception:
            logger.exception("DraftKings spread sync failed")

        try:
            sync_results(app)
        except Exception:
            logger.exception("DraftKings results sync failed")

        try:
            sync_venues(app)
        except Exception:
            logger.exception("ESPN venue sync failed")
