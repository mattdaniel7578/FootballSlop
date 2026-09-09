import os

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from extensions import db, login_manager, oauth


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
    from models import User

    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    with app.app_context():
        db.create_all()

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=os.environ.get("FLASK_ENV") != "production")
