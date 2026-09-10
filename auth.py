from flask import Blueprint, redirect, render_template, request, session, url_for
from flask_login import login_user, logout_user

from extensions import db, oauth
from models import User

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.record_once
def register_google_client(state):
    app = state.app
    oauth.register(
        name="google",
        client_id=app.config["GOOGLE_CLIENT_ID"],
        client_secret=app.config["GOOGLE_CLIENT_SECRET"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


def _is_safe_next(next_url):
    return bool(next_url) and next_url.startswith("/") and not next_url.startswith("//")


@bp.route("/login")
def login():
    # Everything in the app requires login, so most visits arrive here via
    # login_required's own "next" redirect — stash it in the session so
    # start_google() (fired by the button click) can carry it through the
    # OAuth round trip, landing people back where they were headed.
    next_url = request.args.get("next", "")
    if _is_safe_next(next_url):
        session["next"] = next_url

    return render_template("login.html")


@bp.route("/login/google")
def start_google():
    redirect_uri = url_for("auth.callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@bp.route("/callback")
def callback():
    token = oauth.google.authorize_access_token()
    userinfo = token.get("userinfo") or oauth.google.userinfo()

    user = User.query.filter_by(google_sub=userinfo["sub"]).first()
    if user is None:
        # A placeholder account (e.g. picks recorded manually before someone's
        # first login) is matched by email and claimed with their real
        # google_sub, instead of splitting into a duplicate account.
        user = User.query.filter_by(email=userinfo["email"]).first()

    if user is None:
        user = User(
            google_sub=userinfo["sub"],
            email=userinfo["email"],
            name=userinfo.get("name", userinfo["email"]),
            picture=userinfo.get("picture"),
        )
        db.session.add(user)
    else:
        user.google_sub = userinfo["sub"]
        user.email = userinfo["email"]
        user.name = userinfo.get("name", user.name)
        user.picture = userinfo.get("picture")
    db.session.commit()

    # remember=True: once someone has logged in, keep them logged in across
    # browser restarts (see REMEMBER_COOKIE_* in config.py) until they log out.
    login_user(user, remember=True)

    next_url = session.pop("next", None)
    return redirect(next_url if _is_safe_next(next_url) else url_for("main.index"))


@bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
