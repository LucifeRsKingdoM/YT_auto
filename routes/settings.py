from flask import Blueprint, render_template, jsonify

from database import get_session
from models import Admin
from security import login_required
from config import config

bp = Blueprint("settings", __name__)


@bp.route("/settings")
@login_required
def page():
    return render_template("settings.html")


@bp.route("/api/settings")
@login_required
def data():
    s = get_session()
    try:
        admins = s.query(Admin).order_by(Admin.id).all()
        return jsonify({
            "db_mode": config.DB_MODE,
            "admins": [{"username": a.username,
                        "created_at": a.created_at.isoformat() + "Z"
                        if a.created_at else None} for a in admins],
        })
    finally:
        s.close()
