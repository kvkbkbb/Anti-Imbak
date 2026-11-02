"""Authentication: registration, sessions, password recovery and sample access."""
from __future__ import annotations

from datetime import timedelta
import hashlib
import secrets

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import LOCATION_COORDS
from services import (
    CITIES,
    ensure_csrf_token,
    get_db,
    safe_next,
    stamp,
    utcnow,
)

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _email_looks_valid(email: str) -> bool:
    if email.count("@") != 1 or " " in email:
        return False
    local, domain = email.split("@")
    return bool(local) and "." in domain and not domain.startswith(".") and not domain.endswith(".")


def _password_strong(password: str) -> bool:
    return (
        len(password) >= 8
        and any(character.isalpha() for character in password)
        and any(character.isdigit() for character in password)
    )


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.get("user"):
        return redirect(url_for("dashboard.index"))
    next_url = request.values.get("next") or ""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        if not email or not password:
            flash("Enter your email and password to continue.", "error")
            return render_template("auth/login.html", email=email, next_url=next_url), 400
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email,)
        ).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("That email and password combination does not match our records.", "error")
            return render_template("auth/login.html", email=email, next_url=next_url), 401
        if user["status"] == "suspended":
            flash("This account is suspended. Contact hello@antiimbak.ph for assistance.", "error")
            return render_template("auth/login.html", email=email, next_url=next_url), 403
        db.execute("UPDATE users SET last_login = ? WHERE id = ?", (stamp(), user["id"]))
        db.commit()
        session.clear()
        session["user_id"] = user["id"]
        session.permanent = True
        ensure_csrf_token()
        flash(f"Welcome back, {user['name'].split()[0]}.", "success")
        return redirect(safe_next(next_url, url_for("dashboard.index")))
    return render_template("auth/login.html", email="", next_url=next_url)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.get("user"):
        return redirect(url_for("dashboard.index"))
    next_url = request.args.get("next") or ""
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        city = (request.form.get("city") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""
        accepted_terms = request.form.get("terms") == "on"
        errors = []
        if len(name) < 2 or len(name) > 80:
            errors.append("Please add your full name.")
        if not _email_looks_valid(email):
            errors.append("Please enter a valid email address.")
        if city not in CITIES:
            errors.append("Choose the city you usually meet in.")
        if not _password_strong(password):
            errors.append("Your password needs at least 8 characters, including a letter and a number.")
        if password != confirm:
            errors.append("Your passwords do not match yet.")
        if not accepted_terms:
            errors.append("Please accept the community guidelines and terms.")
        db = get_db()
        if not errors:
            existing = db.execute("SELECT id FROM users WHERE email = ? COLLATE NOCASE", (email,)).fetchone()
            if existing:
                errors.append("An account with this email already exists. Try logging in instead.")
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "auth/register.html", form=request.form, next_url=next_url, cities=CITIES
            ), 400
        created = stamp()
        password_hash = generate_password_hash(password)
        latitude, longitude = LOCATION_COORDS[city]
        cur = db.execute(
            """INSERT INTO users (name, email, password_hash, role, status, email_verified, created_at)
               VALUES (?, ?, ?, 'user', 'active', 0, ?)""",
            (name, email, password_hash, created),
        )
        db.execute(
            """INSERT INTO profiles
               (user_id, location, city, latitude, longitude, verified, member_since)
               VALUES (?, ?, ?, ?, ?, 0, ?)""",
            (cur.lastrowid, city, city, latitude, longitude, created),
        )
        user_id = cur.lastrowid
        db.execute(
            "INSERT INTO notifications (user_id, type, title, message, link) VALUES (?, 'announcement', ?, ?, ?)",
            (
                user_id,
                "Welcome to Anti-Imbak",
                "Your account is ready. Browse something useful, save a find, or give an item its next chapter.",
                url_for("public.browse"),
            ),
        )
        db.commit()
        session.clear()
        session["user_id"] = user_id
        session.permanent = True
        ensure_csrf_token()
        flash("Welcome to Anti-Imbak. Giving starts here.", "success")
        return redirect(safe_next(next_url, url_for("dashboard.index")))
    return render_template("auth/register.html", form={}, next_url=next_url, cities=CITIES)


@bp.route("/demo-login/<role>", methods=["POST"])
def demo_login(role: str):
    accounts = {
        "donor": "maya@antiimbak.com",
        "claimant": "josh@antiimbak.com",
        "admin": "admin@antiimbak.com",
    }
    email = accounts.get(role)
    if not email:
        flash("That sample account is not available.", "error")
        return redirect(url_for("auth.login"))
    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE email = ? AND status = 'active'", (email,)
    ).fetchone()
    if user is None:
        flash("Sample accounts have not been seeded yet. Run python db.py.", "error")
        return redirect(url_for("auth.login"))
    db.execute("UPDATE users SET last_login = ? WHERE id = ?", (stamp(), user["id"]))
    db.commit()
    session.clear()
    session["user_id"] = user["id"]
    session.permanent = True
    ensure_csrf_token()
    flash(f"Exploring as {user['name']} ({'administrator' if user['role'] == 'admin' else 'member'}).", "info")
    if user["role"] == "admin":
        return redirect(url_for("admin.overview"))
    next_url = request.form.get("next")
    return redirect(safe_next(next_url, url_for("dashboard.index")))


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You are logged out. Your next good find is still waiting.", "info")
    return redirect(url_for("public.index"))


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    reset_url = None
    email_value = ""
    if request.method == "POST":
        email_value = (request.form.get("email") or "").strip().lower()
        db = get_db()
        user = db.execute(
            "SELECT id, name FROM users WHERE email = ? COLLATE NOCASE AND status = 'active'",
            (email_value,),
        ).fetchone()
        if user:
            token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            expires = (utcnow() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
            db.execute("UPDATE password_resets SET used = 1 WHERE user_id = ? AND used = 0", (user["id"],))
            db.execute(
                "INSERT INTO password_resets (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
                (user["id"], token_hash, expires),
            )
            db.commit()
            reset_url = url_for("auth.reset_password", token=token, _external=False)
        flash(
            "If an account matches that email, a reset link has been prepared. "
            "The local installation has no email provider, so the link appears below instantly.",
            "info",
        )
    return render_template(
        "auth/forgot_password.html", email=email_value, reset_url=reset_url
    )


def _valid_reset_token(token: str):
    if not token:
        return None, None
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    row = get_db().execute(
        """SELECT pr.*, u.name, u.email FROM password_resets pr
           JOIN users u ON u.id = pr.user_id
           WHERE pr.token_hash = ? AND pr.used = 0 AND pr.expires_at > ?""",
        (token_hash, stamp()),
    ).fetchone()
    if row is None:
        return None, None
    return row, token


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    reset, raw_token = _valid_reset_token(token)
    if reset is None:
        flash("That reset link is invalid or has expired. Request a fresh one.", "error")
        return redirect(url_for("auth.forgot_password"))
    if request.method == "POST":
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""
        if not _password_strong(password):
            flash("Your new password needs at least 8 characters, including a letter and a number.", "error")
            return render_template("auth/reset_password.html", reset=reset), 400
        if password != confirm:
            flash("Your new passwords do not match yet.", "error")
            return render_template("auth/reset_password.html", reset=reset), 400
        db = get_db()
        db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(password), reset["user_id"]),
        )
        db.execute("UPDATE password_resets SET used = 1 WHERE user_id = ?", (reset["user_id"],))
        db.commit()
        session.clear()
        flash("Your password has been reset. You can now log in with your new password.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", reset=reset)
