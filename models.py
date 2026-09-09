from datetime import datetime
from zoneinfo import ZoneInfo

from flask_login import UserMixin

from extensions import db

EASTERN = ZoneInfo("America/New_York")


def now_eastern():
    # Naive Eastern-time datetime (America/New_York handles the EST/EDT
    # switch automatically), to match the naive kickoff_at values entered
    # via the admin form (see templates/admin_add_game.html) — avoids
    # aware/naive comparison errors in Game.is_locked().
    return datetime.now(EASTERN).replace(tzinfo=None)


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
    season = db.Column(db.Integer, nullable=False)
    week = db.Column(db.Integer, nullable=False)
    home_team = db.Column(db.String(64), nullable=False)
    away_team = db.Column(db.String(64), nullable=False)

    # Spread is expressed as "favorite_team is favored by spread_points".
    # e.g. favorite_team="Patriots", spread_points=3.5 means Patriots -3.5.
    favorite_team = db.Column(db.String(64), nullable=False)
    spread_points = db.Column(db.Float, nullable=False)

    kickoff_at = db.Column(db.DateTime, nullable=False)
    locked = db.Column(db.Boolean, default=False, nullable=False)
    winner = db.Column(db.String(64))  # set after the game to score picks later

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
