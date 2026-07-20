from flask import (
    Blueprint, render_template, request, redirect, url_for, session, flash
)

from database import get_session
from models import Admin, ActivityLog
from security import check_secret

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        s = get_session()
        try:
            admin = s.query(Admin).filter_by(username=username).one_or_none()
            if admin and check_secret(password, admin.password_hash):
                session["user"] = admin.username
                s.add(ActivityLog(actor=admin.username, action="Signed in"))
                s.commit()
                nxt = request.args.get("next") or url_for("dashboard.page")
                return redirect(nxt)
            flash("Wrong username or password.", "error")
        finally:
            s.close()
    return render_template("login.html")


@bp.route("/logout")
def logout():
    user = session.get("user")
    if user:
        s = get_session()
        try:
            s.add(ActivityLog(actor=user, action="Signed out"))
            s.commit()
        finally:
            s.close()
    session.clear()
    return redirect(url_for("auth.login"))
