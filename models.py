from datetime import datetime
from zoneinfo import ZoneInfo

from flask_login import UserMixin

from extensions import db

EASTERN = ZoneInfo("America/New_York")


def now_eastern():
    # Naive Eastern-time datetime (America/New_York handles the EST/EDT
    # switch automatically), to match the naive kickoff_at values stored on
    # Game — avoids aware/naive comparison errors in Game.is_locked().
    return datetime.now(EASTERN).replace(tzinfo=None)


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


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    google_sub = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    picture = db.Column(db.String(512))
    created_at = db.Column(db.DateTime, default=now_eastern)

    picks = db.relationship("Pick", back_populates="user")


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
