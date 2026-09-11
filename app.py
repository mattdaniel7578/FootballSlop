import os

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from extensions import db, login_manager, oauth

IS_DEBUG = os.environ.get("FLASK_ENV") != "production"


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Render terminates HTTPS at a proxy and forwards plain HTTP internally;
    # without this, url_for(..., _external=True) would build "http://" OAuth
    # redirect URIs that don't match what's registered with Google.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    login_manager.init_app(app)
    oauth.init_app(app)

    import auth
    import main
    from models import User, compute_snap_at, format_snap_eta, short_team_name

    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.jinja_env.filters["short_team"] = short_team_name
    app.jinja_env.filters["snap_eta"] = format_snap_eta
    app.jinja_env.globals["compute_snap_at"] = compute_snap_at

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    with app.app_context():
        db.create_all()

    _start_odds_scheduler(app)

    return app


def _start_odds_scheduler(app):
    # The debug reloader runs two processes; only the child (which actually
    # serves requests) should own the scheduler, or jobs would fire twice.
    if IS_DEBUG and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return

    from apscheduler.schedulers.background import BackgroundScheduler

    import odds

    scheduler = BackgroundScheduler(daemon=True, timezone=odds.EASTERN)
    odds.start_scheduler(app, scheduler)


if __name__ == "__main__":
    app = create_app()
    app.run(debug=IS_DEBUG)
