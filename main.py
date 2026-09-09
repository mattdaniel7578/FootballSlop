from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import Game, Pick

bp = Blueprint("main", __name__)


def admin_required():
    if not current_user.is_authenticated or not current_user.is_admin():
        abort(403)


@bp.route("/")
def index():
    games = Game.query.order_by(Game.kickoff_at).all()

    my_picks = {}
    if current_user.is_authenticated:
        picks = Pick.query.filter_by(user_id=current_user.id).all()
        my_picks = {p.game_id: p.picked_team for p in picks}

    return render_template("index.html", games=games, my_picks=my_picks)


@bp.route("/games/<int:game_id>/pick", methods=["POST"])
@login_required
def make_pick(game_id):
    game = Game.query.get_or_404(game_id)

    if game.is_locked():
        flash("Picks are locked for this game — kickoff has passed.", "error")
        return redirect(url_for("main.index"))

    picked_team = request.form.get("picked_team")
    if picked_team not in (game.home_team, game.away_team):
        flash("Invalid team selected.", "error")
        return redirect(url_for("main.index"))

    pick = Pick.query.filter_by(user_id=current_user.id, game_id=game.id).first()
    if pick is None:
        pick = Pick(user_id=current_user.id, game_id=game.id, picked_team=picked_team)
        db.session.add(pick)
    else:
        pick.picked_team = picked_team

    db.session.commit()
    flash(f"Pick saved: {picked_team} ({game.spread_display(picked_team)}).", "success")
    return redirect(url_for("main.index"))


@bp.route("/admin/games/new", methods=["GET", "POST"])
@login_required
def new_game():
    admin_required()

    if request.method == "POST":
        try:
            game = Game(
                season=int(request.form["season"]),
                week=int(request.form["week"]),
                home_team=request.form["home_team"].strip(),
                away_team=request.form["away_team"].strip(),
                favorite_team=request.form["favorite_team"].strip(),
                spread_points=float(request.form["spread_points"]),
                kickoff_at=datetime.fromisoformat(request.form["kickoff_at"]),
            )
        except (KeyError, ValueError):
            flash("Please fill out every field with valid values.", "error")
            return redirect(url_for("main.new_game"))

        if game.favorite_team not in (game.home_team, game.away_team):
            flash("Favorite team must match the home or away team name.", "error")
            return redirect(url_for("main.new_game"))

        db.session.add(game)
        db.session.commit()
        flash("Game added.", "success")
        return redirect(url_for("main.index"))

    return render_template("admin_add_game.html")
