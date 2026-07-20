"""Application entry point.

Run:
    python app.py
It seeds the two admin accounts, creates tables, starts the scheduler, and
serves the UI on http://localhost:5000
"""
from flask import Flask, redirect

from config import config
from database import init_db, SessionLocal
from seed import seed_admins
import scheduler

from routes import (
    auth, dashboard, videos, schedule, analytics, integrations, settings,
)


def create_app():
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY

    # 100 MB upload cap by default (videos can be large; raise if needed)
    app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # 1 GB

    # database + admins
    init_db()
    seed_admins()

    # blueprints
    app.register_blueprint(auth.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(videos.bp)
    app.register_blueprint(schedule.bp)
    app.register_blueprint(analytics.bp)
    app.register_blueprint(integrations.bp)
    app.register_blueprint(settings.bp)

    @app.teardown_appcontext
    def remove_session(exc=None):
        SessionLocal.remove()

    @app.route("/healthz")
    def healthz():
        return {"ok": True}

    return app


app = create_app()
# start the background scheduler once, in the main process
scheduler.start_scheduler()


if __name__ == "__main__":
    # threaded so uploads don't block the UI; single process so the
    # scheduler runs exactly once.
    app.run(host="0.0.0.0", port=5000, threaded=True, use_reloader=False)
