"""Role-view helpers: quick perspective switching, access prompts and reset."""
from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from db import reset_database
from services import (
    DEMO_ACCOUNTS,
    DEMO_ROLES,
    close_db,
    ensure_csrf_token,
    get_db,
    get_listing_detail,
    safe_next,
    stamp,
)

bp = Blueprint("demo", __name__, url_prefix="/demo")

ROLE_HOME = {
    "donor": "dashboard.donations",
    "recipient": "dashboard.my_claims",
    "admin": "admin.overview",
}


@bp.route("/access")
def access():
    """A friendly account prompt for guest-only actions."""
    intent = (request.args.get("intent") or "claim").strip()
    if intent not in {"claim", "donate", "save", "request", "message"}:
        intent = "claim"
    listing = None
    listing_id = request.args.get("listing_id", type=int)
    if listing_id:
        listing = get_listing_detail(listing_id)
    if intent in {"claim", "request", "save", "message"} and listing is None and listing_id:
        abort(404)

    if listing:
        target = url_for("public.listing_detail", listing_id=listing["id"]) + "?claim=1"
    elif intent == "donate":
        target = url_for("dashboard.new_donation")
    elif intent == "save":
        target = url_for("dashboard.saved")
    elif intent == "message":
        target = url_for("dashboard.messages")
    else:
        target = url_for("public.browse")

    copy = {
        "claim": {
            "eyebrow": "Claiming needs a community account",
            "title": "This is a request, not a purchase.",
            "lede": "A claim tells a Donor why an item matters to you. Sign in or create a free account to send a request and arrange Partnered Delivery or Self Pickup.",
        },
        "donate": {
            "eyebrow": "Giving needs a community account",
            "title": "Give something a second purpose.",
            "lede": "Donors create free listings, review interested Recipients and coordinate every handover through Messages.",
        },
        "save": {
            "eyebrow": "Saving needs a community account",
            "title": "Keep the good finds close.",
            "lede": "Saved items follow you across the marketplace. Sign in to keep a shortlist and return when you are ready.",
        },
        "request": {
            "eyebrow": "Your request is waiting",
            "title": "Track every handover in one place.",
            "lede": "Requests, Partnered Delivery updates and conversations live together in your account.",
        },
        "message": {
            "eyebrow": "Messaging needs a community account",
            "title": "Ask before you claim.",
            "lede": "Message the Donor about condition, measurements or photos, then decide whether the item is right for you.",
        },
    }[intent]
    return render_template(
        "demo/access.html",
        intent=intent,
        listing=listing,
        target=target,
        copy=copy,
    )


@bp.route("/switch/<role>", methods=["POST"])
def switch(role: str):
    if role not in DEMO_ROLES:
        abort(404)
    if role == "public":
        session.clear()
        ensure_csrf_token()
        flash("You are now browsing as a public visitor.", "info")
        return redirect(url_for("public.index"))

    db = get_db()
    user = db.execute(
        "SELECT id, name, email, role, status FROM users WHERE email = ?",
        (DEMO_ACCOUNTS[role],),
    ).fetchone()
    if user is None:
        flash("That sample account is missing. Reset the sample data to restore it.", "error")
        return redirect(url_for("public.index"))
    if user["status"] != "active":
        db.execute("UPDATE users SET status = 'active' WHERE id = ?", (user["id"],))
        db.commit()

    session.clear()
    session["user_id"] = user["id"]
    session["demo_role"] = role
    session.permanent = True
    ensure_csrf_token()
    db.execute("UPDATE users SET last_login = ? WHERE id = ?", (stamp(), user["id"]))
    db.commit()

    default_target = url_for(ROLE_HOME[role])
    target = safe_next(request.form.get("next"), default_target)
    if role != "admin" and target.startswith("/admin"):
        target = default_target
    if role == "donor" and target.startswith(("/dashboard/saved", "/dashboard/claims/mine")):
        target = default_target
    if role == "recipient" and target.startswith(("/dashboard/claims", "/dashboard/donations")):
        if not target.startswith("/dashboard/claims/mine"):
            target = default_target
    flash(f"Viewing as {DEMO_ROLES[role]['label']} — {user['name']}.", "success")
    return redirect(target)


@bp.route("/reset", methods=["POST"])
def reset():
    close_db()
    reset_database()
    session.clear()
    ensure_csrf_token()
    flash(
        "Sample data restored. Listings, requests, conversations, disputes, concerns and revenue are back to their original state.",
        "success",
    )
    return redirect(url_for("public.index"))
