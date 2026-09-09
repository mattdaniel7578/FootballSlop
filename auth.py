from flask import Blueprint, redirect, url_for
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


@bp.route("/login")
def login():
    redirect_uri = url_for("auth.callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@bp.route("/callback")
def callback():
    token = oauth.google.authorize_access_token()
    userinfo = token.get("userinfo") or oauth.google.userinfo()

    user = User.query.filter_by(google_sub=userinfo["sub"]).first()
    if user is None:
        user = User(
            google_sub=userinfo["sub"],
            email=userinfo["email"],
            name=userinfo.get("name", userinfo["email"]),
            picture=userinfo.get("picture"),
        )
        db.session.add(user)
    else:
        user.email = userinfo["email"]
        user.name = userinfo.get("name", user.name)
        user.picture = userinfo.get("picture")
    db.session.commit()

    login_user(user)
    return redirect(url_for("main.index"))


@bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("main.index"))
