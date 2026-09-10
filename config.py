import os
from datetime import date, timedelta

from dotenv import load_dotenv

load_dotenv()

# Render (and Heroku-style hosts) inject Postgres URLs as "postgres://", but
# SQLAlchemy's modern driver requires "postgresql://".
_database_url = os.environ.get("DATABASE_URL", "sqlite:///pool.db")
if _database_url.startswith("postgres://"):
    _database_url = _database_url.replace("postgres://", "postgresql://", 1)

IS_PRODUCTION = os.environ.get("FLASK_ENV") == "production"

# Anchors week numbering: the Tuesday that Week 1 starts on (NFL weeks run
# Tue-Mon). Without it, games are still synced but all default to week 1.
_season_start = os.environ.get("SEASON_START_DATE", "")
SEASON_START_DATE = date.fromisoformat(_season_start) if _season_start else None


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key")
    SQLALCHEMY_DATABASE_URI = _database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    # From https://the-odds-api.com/ — used to pull DraftKings spreads and
    # final scores automatically instead of manual entry (see odds.py).
    ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "")
    ODDS_SYNC_MINUTES = int(os.environ.get("ODDS_SYNC_MINUTES", "60"))
    SEASON_START_DATE = SEASON_START_DATE

    SESSION_COOKIE_SECURE = IS_PRODUCTION
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # "Remember me" cookie (see login_user(..., remember=True) in auth.py) —
    # keeps someone logged in across browser restarts until they log out.
    REMEMBER_COOKIE_DURATION = timedelta(days=365)
    REMEMBER_COOKIE_SECURE = IS_PRODUCTION
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
