from collections import defaultdict
from itertools import groupby

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import SLATE_LABELS, Game, Pick, User, now_eastern

bp = Blueprint("main", __name__)


def current_season():
    return db.session.query(db.func.max(Game.season)).scalar()


def current_week(season):
    """The soonest week that isn't fully finished yet, or the last week if
    the whole season's games have already kicked off."""
    weeks = (
        db.session.query(Game.week, db.func.max(Game.kickoff_at))
        .filter_by(season=season)
        .group_by(Game.week)
        .order_by(Game.week)
        .all()
    )
    if not weeks:
        return 1

    now = now_eastern()
    for week, last_kickoff in weeks:
        if last_kickoff >= now:
            return week
    return weeks[-1][0]


@bp.route("/")
def index():
    season = current_season()
    weeks = []
    week = None
    games = []

    if season is not None:
        week_cap = current_week(season)
        # Don't reveal future weeks until the current one is over.
        weeks = [
            w
            for (w,) in db.session.query(Game.week)
            .filter(Game.season == season, Game.week <= week_cap)
            .distinct()
            .order_by(Game.week)
            .all()
        ]
        requested_week = request.args.get("week", type=int)
        week = requested_week if requested_week in weeks else week_cap
        games = (
            Game.query.filter_by(season=season, week=week).order_by(Game.kickoff_at).all()
        )

    my_picks = {}
    if current_user.is_authenticated:
        picks = Pick.query.filter_by(user_id=current_user.id).all()
        my_picks = {p.game_id: p.picked_team for p in picks}

    # Consecutive runs of the same slate, in kickoff order — e.g. a Thursday
    # primetime game forms its own leading group, separate from the
    # Sunday/Monday-night primetime group that follows the early/late games.
    slate_groups = [
        {"slate": slate, "games": list(games_in_slate)}
        for slate, games_in_slate in groupby(games, key=lambda g: g.slate)
    ]

    pick_breakdowns = {}
    locked_game_ids = [g.id for g in games if g.is_locked()]
    if locked_game_ids:
        entries_by_game = defaultdict(list)
        locked_picks = (
            Pick.query.filter(Pick.game_id.in_(locked_game_ids))
            .join(User)
            .order_by(User.name)
            .all()
        )
        for p in locked_picks:
            entries_by_game[p.game_id].append((p.user.name, p.picked_team))

        for game in games:
            if game.id not in locked_game_ids:
                continue
            entries = entries_by_game.get(game.id, [])
            total = len(entries)
            home_names = [name for name, team in entries if team == game.home_team]
            away_names = [name for name, team in entries if team == game.away_team]
            pick_breakdowns[game.id] = {
                "total": total,
                "home_names": home_names,
                "away_names": away_names,
                "home_pct": round(len(home_names) / total * 100) if total else 0,
                "away_pct": round(len(away_names) / total * 100) if total else 0,
            }

    return render_template(
        "picks.html",
        games=games,
        slate_groups=slate_groups,
        slate_labels=SLATE_LABELS,
        pick_breakdowns=pick_breakdowns,
        my_picks=my_picks,
        season=season,
        week=week,
        weeks=weeks,
    )


@bp.route("/games/<int:game_id>/pick", methods=["POST"])
@login_required
def make_pick(game_id):
    game = Game.query.get_or_404(game_id)

    if game.is_locked():
        flash("Picks are locked for this game — kickoff has passed.", "error")
        return redirect(url_for("main.index", week=game.week))

    picked_team = request.form.get("picked_team")
    if picked_team not in (game.home_team, game.away_team):
        flash("Invalid team selected.", "error")
        return redirect(url_for("main.index", week=game.week))

    if game.slate in ("early", "late"):
        # Only one pick is allowed per early/late slate — picking a
        # different game in the same slate replaces the earlier one.
        slate_game_ids = [
            g.id
            for g in Game.query.filter_by(
                season=game.season, week=game.week, slate=game.slate
            ).with_entities(Game.id)
            if g.id != game.id
        ]
        if slate_game_ids:
            Pick.query.filter(
                Pick.user_id == current_user.id, Pick.game_id.in_(slate_game_ids)
            ).delete(synchronize_session=False)

    pick = Pick.query.filter_by(user_id=current_user.id, game_id=game.id).first()
    if pick is None:
        pick = Pick(user_id=current_user.id, game_id=game.id, picked_team=picked_team)
        db.session.add(pick)
    else:
        pick.picked_team = picked_team

    db.session.commit()
    flash(f"Pick saved: {picked_team} ({game.spread_display(picked_team)}).", "success")
    return redirect(url_for("main.index", week=game.week))


@bp.route("/leaderboard")
def leaderboard():
    users = User.query.order_by(User.name).all()

    records = []
    for user in users:
        decided_picks = (
            Pick.query.filter_by(user_id=user.id)
            .join(Game)
            .filter(Game.winner.isnot(None), Game.winner != "PUSH")
            .all()
        )
        wins = sum(1 for p in decided_picks if p.picked_team == p.game.winner)
        losses = len(decided_picks) - wins
        records.append({"user": user, "wins": wins, "losses": losses})

    records.sort(key=lambda r: (-r["wins"], r["losses"], r["user"].name.lower()))
    return render_template("leaderboard.html", records=records)


@bp.route("/leaderboard/<int:user_id>")
def user_picks(user_id):
    picked_user = User.query.get_or_404(user_id)
    picks = (
        Pick.query.filter_by(user_id=user_id)
        .join(Game)
        .order_by(Game.season.desc(), Game.week.desc(), Game.kickoff_at)
        .all()
    )
    return render_template("user_picks.html", picked_user=picked_user, picks=picks)


@bp.route("/rules")
def rules():
    return render_template("rules.html")
