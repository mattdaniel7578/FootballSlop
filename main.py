from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import SLATE_LABELS, Game, Pick, User, now_eastern

bp = Blueprint("main", __name__)

SLATE_ORDER = ["primetime", "early", "late"]


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

    games_by_slate = {slate: [] for slate in SLATE_ORDER}
    for game in games:
        games_by_slate.setdefault(game.slate, []).append(game)

    slate_picks = {}
    for slate, slate_games in games_by_slate.items():
        picked_game_id = next((g.id for g in slate_games if g.id in my_picks), None)
        if picked_game_id is not None:
            slate_picks[slate] = my_picks[picked_game_id]

    return render_template(
        "picks.html",
        games=games,
        games_by_slate=games_by_slate,
        slate_order=SLATE_ORDER,
        slate_labels=SLATE_LABELS,
        slate_picks=slate_picks,
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
