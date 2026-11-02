"""Anti-Imbak application factory and cross-cutting concerns."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from flask import Flask, g, render_template, request

from db import DATABASE_PATH, init_db
import services
from services import (
    close_db,
    compact_money,
    condition_tone,
    current_perspective,
    ensure_csrf_token,
    get_categories,
    initials,
    load_logged_in_user,
    long_date,
    money,
    plural,
    priority_tone,
    run_expirations,
    status_tone,
    time_ago,
    unread_message_count,
    unread_notification_count,
    validate_csrf,
)

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)


def _secret_key() -> str:
    env_key = os.environ.get("ANTI_IMBAK_SECRET")
    if env_key:
        return env_key
    key_file = INSTANCE_DIR / "secret.key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    key_file.write_text(key, encoding="utf-8")
    return key


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=_secret_key(),
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("ANTI_IMBAK_COOKIE_SECURE", "0") == "1",
        PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 14,
        TEMPLATES_AUTO_RELOAD=True,
        DATABASE=str(DATABASE_PATH),
    )

    init_db()

    app.teardown_appcontext(close_db)

    @app.before_request
    def before_request():
        if request.endpoint == "static":
            return
        load_logged_in_user()
        ensure_csrf_token()
        validate_csrf()
        run_expirations()

    @app.context_processor
    def inject_layout_context():
        if request.endpoint == "static":
            return {}
        if "nav_categories" not in g:
            g.nav_categories = get_categories()
        nav_counts = {"incoming": 0, "claims": 0, "deliveries": 0, "reports": 0, "disputes": 0, "concerns": 0}
        endpoint = request.endpoint or ""
        if g.get("user"):
            db = services.get_db()
            nav_counts["messages"] = unread_message_count()
            nav_counts["notifications"] = unread_notification_count()
            if endpoint.startswith(("dashboard.", "admin.")):
                nav_counts["incoming"] = db.execute(
                    """SELECT COUNT(*) FROM claims c JOIN listings l ON l.id = c.listing_id
                       WHERE l.donor_id = ? AND c.status = 'pending'""",
                    (g.user["id"],),
                ).fetchone()[0]
                nav_counts["claims"] = db.execute(
                    "SELECT COUNT(*) FROM claims WHERE claimant_id = ? AND status IN ('pending', 'accepted')",
                    (g.user["id"],),
                ).fetchone()[0]
                nav_counts["deliveries"] = db.execute(
                    """SELECT COUNT(*) FROM delivery_requests d JOIN listings l ON l.id = d.listing_id
                       WHERE (d.requester_id = ? OR l.donor_id = ?)
                         AND d.status IN ('request_accepted', 'awaiting_dispatch', 'in_progress', 'arriving_soon')""",
                    (g.user["id"], g.user["id"]),
                ).fetchone()[0]
                if g.user["role"] == "admin":
                    nav_counts["reports"] = db.execute(
                        "SELECT COUNT(*) FROM reports WHERE status = 'open'"
                    ).fetchone()[0]
                    nav_counts["disputes"] = db.execute(
                        "SELECT COUNT(*) FROM disputes WHERE status IN ('open', 'under_review')"
                    ).fetchone()[0]
                    nav_counts["concerns"] = db.execute(
                        "SELECT COUNT(*) FROM support_concerns WHERE status IN ('open', 'in_progress')"
                    ).fetchone()[0]
        return {
            "current_user": g.get("user"),
            "nav_categories": g.get("nav_categories", []),
            "unread_notifications": unread_notification_count(),
            "unread_messages": unread_message_count(),
            "nav_counts": nav_counts,
            "csrf_token": ensure_csrf_token(),
            "current_year": services.utcnow().year,
            "cities": services.CITIES,
            "conditions": services.CONDITIONS,
            "condition_labels": services.CONDITION_LABELS,
            "item_sizes": services.ITEM_SIZES,
            "item_size_labels": services.ITEM_SIZE_LABELS,
            "delivery_steps": services.DELIVERY_STEPS,
            "delivery_step_copy": services.DELIVERY_STEP_COPY,
            "delivery_fee_min": services.DELIVERY_FEE_MIN,
            "delivery_fee_max": services.DELIVERY_FEE_MAX,
            "demo_role": current_perspective(),
            "demo_roles": services.DEMO_ROLES,
            "demo_accounts": services.DEMO_ACCOUNTS,
        }

    app.jinja_env.filters.update(
        {
            "time_ago": time_ago,
            "money": money,
            "compact_money": compact_money,
            "long_date": long_date,
            "initials": initials,
            "plural": plural,
            "status_tone": status_tone,
            "condition_tone": condition_tone,
            "priority_tone": priority_tone,
            "status_label": lambda value: services.LISTING_STATUS_LABELS.get(value, value or ""),
            "claim_status_label": lambda value: services.CLAIM_STATUS_LABELS.get(value, value or ""),
            "delivery_status_label": lambda value: services.DELIVERY_STATUS_LABELS.get(value, value or ""),
            "dispute_status_label": lambda value: services.DISPUTE_STATUS_LABELS.get(value, value or ""),
            "support_status_label": lambda value: services.SUPPORT_STATUS_LABELS.get(value, value or ""),
            "priority_label": lambda value: services.PRIORITY_LABELS.get(value, value or ""),
            "item_size_label": lambda value: services.ITEM_SIZE_LABELS.get(value, value or ""),
            "condition_label": lambda value: services.CONDITION_LABELS.get(value, value or ""),
        }
    )
    app.jinja_env.globals.update(
        status_label=lambda value: services.LISTING_STATUS_LABELS.get(value, value or ""),
        claim_status_label=lambda value: services.CLAIM_STATUS_LABELS.get(value, value or ""),
        delivery_status_label=lambda value: services.DELIVERY_STATUS_LABELS.get(value, value or ""),
        dispute_status_label=lambda value: services.DISPUTE_STATUS_LABELS.get(value, value or ""),
        support_status_label=lambda value: services.SUPPORT_STATUS_LABELS.get(value, value or ""),
        priority_label=lambda value: services.PRIORITY_LABELS.get(value, value or ""),
        delivery_steps=services.DELIVERY_STEPS,
        listing_statuses=services.LISTING_STATUSES,
        report_reasons=services.REPORT_REASONS,
        featured_packages=services.FEATURED_PACKAGES,
        conditions_list=services.CONDITIONS,
        dispute_categories=services.DISPUTE_CATEGORIES,
        dispute_statuses=services.DISPUTE_STATUSES,
        dispute_priorities=services.DISPUTE_PRIORITIES,
        support_categories=services.SUPPORT_CATEGORIES,
        support_statuses=services.SUPPORT_STATUSES,
        demo_roles_list=[{"key": key, **value} for key, value in services.DEMO_ROLES.items()],
    )

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; font-src 'self'; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; "
            "form-action 'self'; frame-ancestors 'self'; base-uri 'self'",
        )
        if response.content_type and response.content_type.startswith("text/html"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    from routes.public import bp as public_bp
    from routes.auth import bp as auth_bp
    from routes.dashboard import bp as dashboard_bp
    from routes.admin import bp as admin_bp
    from routes.api import bp as api_bp
    from routes.demo import bp as demo_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(demo_bp)

    @app.errorhandler(400)
    def bad_request(error):
        message = getattr(error, "description", "The request could not be completed.")
        return render_template("error.html", code=400, title="That request needs a refresh",
                               message=message), 400

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template(
            "error.html", code=403, title="This space is not yours to open",
            message="Your account does not have permission to view this page."
        ), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template(
            "error.html", code=404, title="This page has found a new purpose",
            message="The page or listing you are looking for is no longer here. It may have been removed, claimed, or moved."
        ), 404

    @app.errorhandler(413)
    def too_large(_error):
        return render_template(
            "error.html", code=413, title="That upload is a little too heavy",
            message="Please keep each image under 5 MB and the total upload under 8 MB."
        ), 413

    @app.errorhandler(500)
    def server_error(_error):
        return render_template(
            "error.html", code=500, title="A small hiccup on our side",
            message="Something unexpected happened. Please try again, or return to the marketplace."
        ), 500

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
