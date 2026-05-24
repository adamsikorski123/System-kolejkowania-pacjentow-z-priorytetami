from flask import Blueprint, request, session, redirect, url_for, render_template, make_response # importowanie potrzebnych funkcji i klas z frameworka Flask
import time # standardowa biblioteka do obsługi czasu

auth_bp = Blueprint("auth", __name__)

def init_auth(app, patient_db):
    patient_db.ensure_default_user()
    app.config["AUTH_BOOT_ID"] = str(time.time_ns())

    @auth_bp.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            if patient_db.verify_user(username, password):
                session.clear()
                session["user"] = username
                session["boot_id"] = app.config["AUTH_BOOT_ID"]
                return redirect(url_for("patient_form"))
            return render_template("login.html", error="Nieprawidłowy login lub hasło.")
        return render_template("login.html", error=None)

    @auth_bp.route("/logout", methods=["GET"])
    def logout():
        session.clear()
        response = make_response(redirect(url_for("auth.login")))
        response.delete_cookie(app.config.get("SESSION_COOKIE_NAME", "session"))
        return response

    @app.context_processor
    def inject_current_user():
        return {"current_user": session.get("user")}

    @app.before_request
    def require_login():
        allowed = {"auth.login", "static"}
        if request.endpoint in allowed:
            return None
        if request.endpoint == "auth.logout":
            return None

        # wymuszenie logowania po każdym restarcie API
        if session.get("boot_id") != app.config.get("AUTH_BOOT_ID"):
            session.clear()
            return redirect(url_for("auth.login"))

        if not session.get("user"):
            return redirect(url_for("auth.login"))

    app.register_blueprint(auth_bp)
