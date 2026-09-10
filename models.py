from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from flask_login import UserMixin

from extensions import db

EASTERN = ZoneInfo("America/New_York")


def now_eastern():
    # Naive Eastern-time datetime (America/New_York handles the EST/EDT
    # switch automatically), to match the naive kickoff_at values stored on
    # Game — avoids aware/naive comparison errors in Game.is_locked().
    return datetime.now(EASTERN).replace(tzinfo=None)


def short_team_name(full_name):
    """"New England Patriots" -> "Patriots" — display only; the full name
    is still what's stored/submitted/matched against favorite_team."""
    return full_name.rsplit(" ", 1)[-1] if full_name else full_name


SLATE_LABELS = {
    "primetime": "Primetime",
    "early": "Early games (1:00 PM ET + London)",
    "late": "Late games (4:05 / 4:25 PM ET)",
}


def classify_slate(kickoff_et):
    """Bucket a naive-ET kickoff into a picks slate.

    Thu/Mon standalone games are always primetime. Sat/Sun games split by
    kickoff hour into early (~9:30am London + 1:00pm ET), late (4:05/4:25pm
    ET), or primetime (Sun/Sat night). Any other standalone weekday game
    (e.g. a Black Friday game) defaults to primetime.
    """
    weekday = kickoff_et.weekday()  # Mon=0 ... Sun=6
    if weekday in (5, 6):  # Saturday, Sunday
        if kickoff_et.hour < 16:
            return "early"
        if kickoff_et.hour < 20:
            return "late"
        return "primetime"
    return "primetime"


def compute_snap_at(kickoff_et):
    """When a game's DraftKings line should freeze, ahead of kickoff:

    - Thursday games: the preceding Wednesday at 4:00 PM ET.
    - Sunday or Monday games: the preceding Saturday at 1:00 PM ET.
    - Anything else (e.g. a Saturday game): 24 hours before kickoff.
    """
    weekday = kickoff_et.weekday()  # Mon=0 ... Sun=6
    if weekday == 3:  # Thursday
        wednesday = kickoff_et.date() - timedelta(days=1)
        return datetime.combine(wednesday, time(16, 0))
    if weekday in (6, 0):  # Sunday, Monday
        days_back = 1 if weekday == 6 else 2
        saturday = kickoff_et.date() - timedelta(days=days_back)
        return datetime.combine(saturday, time(13, 0))
    return kickoff_et - timedelta(hours=24)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    google_sub = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    picture = db.Column(db.String(512))
    created_at = db.Column(db.DateTime, default=now_eastern)

    picks = db.relationship("Pick", back_populates="user")

    def is_admin(self):
        from flask import current_app

        return self.email.lower() in current_app.config["ADMIN_EMAILS"]


class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # The-Odds-API event id, used to upsert games on each DraftKings sync
    # instead of creating duplicates (see odds.py).
    external_id = db.Column(db.String(64), unique=True)

    season = db.Column(db.Integer, nullable=False)
    week = db.Column(db.Integer, nullable=False)

    # Which picks slate this game belongs to: "primetime" (pick every one),
    # "early", or "late" (pick exactly one game per slate). See
    # classify_slate() above.
    slate = db.Column(db.String(16), nullable=False, default="primetime")

    home_team = db.Column(db.String(64), nullable=False)
    away_team = db.Column(db.String(64), nullable=False)

    # Spread is expressed as "favorite_team is favored by spread_points".
    # e.g. favorite_team="Patriots", spread_points=3.5 means Patriots -3.5.
    favorite_team = db.Column(db.String(64), nullable=False)
    spread_points = db.Column(db.Float, nullable=False)

    kickoff_at = db.Column(db.DateTime, nullable=False)
    locked = db.Column(db.Boolean, default=False, nullable=False)

    # When the DraftKings line actually stopped updating (see
    # compute_snap_at() and odds.sync_spreads) — None while it's still live.
    line_snapshot_at = db.Column(db.DateTime)

    # "Venue, City, ST/Country" — pulled from ESPN's scoreboard (see
    # odds.sync_venues), since it correctly reflects neutral-site/
    # international games instead of assuming the home team's own stadium.
    location = db.Column(db.String(255))

    # Set once final: the ATS winner's team name, "PUSH" if the final margin
    # landed exactly on the spread, or None while the game is undecided.
    winner = db.Column(db.String(64))

    picks = db.relationship("Pick", back_populates="game", cascade="all, delete-orphan")

    def underdog_team(self):
        return self.away_team if self.favorite_team == self.home_team else self.home_team

    def is_locked(self):
        return self.locked or now_eastern() >= self.kickoff_at

    def spread_display(self, team):
        if team == self.favorite_team:
            return f"-{self.spread_points:g}"
        return f"+{self.spread_points:g}"


class Pick(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey("game.id"), nullable=False)
    picked_team = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, default=now_eastern)
    updated_at = db.Column(db.DateTime, default=now_eastern, onupdate=now_eastern)

    user = db.relationship("User", back_populates="picks")
    game = db.relationship("Game", back_populates="picks")

    __table_args__ = (db.UniqueConstraint("user_id", "game_id", name="uq_user_game_pick"),)
