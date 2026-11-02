"""Administrator dashboard: moderation, revenue, users and content controls."""
from __future__ import annotations

import csv
import io
from datetime import timedelta

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from services import (
    DISPUTE_STATUSES,
    SUPPORT_STATUSES,
    admin_required,
    get_categories,
    get_db,
    is_safe_redirect_url,
    log_admin,
    notify,
    slugify,
    stamp,
    utcnow,
)

bp = Blueprint("admin", __name__, url_prefix="/admin")

ALLOWED_AD_IMAGES = {
    "moving": "/static/img/ads/moving.jpg",
    "cleaning": "/static/img/ads/cleaning.jpg",
    "repair": "/static/img/ads/repair.jpg",
    "truck": "/static/img/ads/truck.jpg",
    "none": "",
}
CATEGORY_ICONS = [
    "monitor", "armchair", "shirt", "fridge", "book", "gamepad",
    "dumbbell", "utensils", "box", "lamp", "bicycle",
]


@bp.before_request
def guard_admin():
    if g.get("user") is None:
        flash("Log in with an administrator account to continue.", "info")
        from services import safe_next

        return redirect(
            url_for("auth.login", next=safe_next(request.full_path.rstrip("?")))
        )
    if g.user["role"] != "admin":
        abort(403)
    return None


def _sum_transactions(transaction_type: str) -> float:
    row = get_db().execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = ? AND status = 'completed'",
        (transaction_type,),
    ).fetchone()
    return round(float(row[0] if row else 0), 2)


def _platform_fees(transaction_type: str) -> float:
    row = get_db().execute(
        "SELECT COALESCE(SUM(platform_fee), 0) FROM transactions WHERE type = ? AND status = 'completed'",
        (transaction_type,),
    ).fetchone()
    return round(float(row[0] if row else 0), 2)


@bp.route("/")
def overview():
    db = get_db()
    now = utcnow()
    stats = {
        "total_users": db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "active_users": db.execute("SELECT COUNT(*) FROM users WHERE status = 'active'").fetchone()[0],
        "total_listings": db.execute("SELECT COUNT(*) FROM listings WHERE status != 'removed'").fetchone()[0],
        "successful_claims": db.execute("SELECT COUNT(*) FROM claims WHERE status = 'completed'").fetchone()[0],
        "pending_claims": db.execute("SELECT COUNT(*) FROM claims WHERE status = 'pending'").fetchone()[0],
        "open_reports": db.execute("SELECT COUNT(*) FROM reports WHERE status = 'open'").fetchone()[0],
        "open_disputes": db.execute(
            "SELECT COUNT(*) FROM disputes WHERE status IN ('open', 'under_review')"
        ).fetchone()[0],
        "open_concerns": db.execute(
            "SELECT COUNT(*) FROM support_concerns WHERE status IN ('open', 'in_progress')"
        ).fetchone()[0],
        "active_ads": db.execute(
            "SELECT COUNT(*) FROM advertisements WHERE status = 'active' AND ends_at >= ?", (stamp(),)
        ).fetchone()[0],
        "featured_revenue": _sum_transactions("featured"),
        "delivery_fees": _sum_transactions("delivery"),
        "ad_revenue": _sum_transactions("advertisement"),
    }
    stats["total_revenue"] = round(
        stats["featured_revenue"] + stats["ad_revenue"], 2
    )

    # Seven-day activity, always computed from actual rows.
    days = []
    for offset in range(6, -1, -1):
        day = (now - timedelta(days=offset)).date()
        key = day.isoformat()
        listings_count = db.execute(
            "SELECT COUNT(*) FROM listings WHERE date(created_at) = ?", (key,)
        ).fetchone()[0]
        users_count = db.execute(
            "SELECT COUNT(*) FROM users WHERE date(created_at) = ?", (key,)
        ).fetchone()[0]
        claims_count = db.execute(
            "SELECT COUNT(*) FROM claims WHERE date(created_at) = ?", (key,)
        ).fetchone()[0]
        days.append(
            {
                "label": day.strftime("%a"),
                "date": day.strftime("%b %d"),
                "listings": listings_count,
                "users": users_count,
                "claims": claims_count,
            }
        )
    max_activity = max(1, max(day["listings"] + day["users"] + day["claims"] for day in days))

    category_counts = db.execute(
        """SELECT c.name, c.icon, COUNT(l.id) AS total FROM categories c
           LEFT JOIN listings l ON l.category_id = c.id AND l.status != 'removed'
           GROUP BY c.id ORDER BY total DESC, c.name"""
    ).fetchall()
    max_category = max(1, max((row["total"] for row in category_counts), default=0))

    recent_reports = db.execute(
        """SELECT r.*, l.title AS listing_title, reporter.name AS reporter_name
           FROM reports r LEFT JOIN listings l ON l.id = r.listing_id
           JOIN users reporter ON reporter.id = r.reporter_id
           WHERE r.status = 'open' ORDER BY r.created_at DESC LIMIT 4"""
    ).fetchall()
    pending_claims = db.execute(
        """SELECT c.*, l.title AS listing_title, u.name AS claimant_name
           FROM claims c JOIN listings l ON l.id = c.listing_id
           JOIN users u ON u.id = c.claimant_id
           WHERE c.status = 'pending' ORDER BY c.created_at DESC LIMIT 4"""
    ).fetchall()
    recent_transactions = db.execute(
        """SELECT t.*, u.name AS user_name FROM transactions t
           LEFT JOIN users u ON u.id = t.user_id
           ORDER BY t.created_at DESC LIMIT 5"""
    ).fetchall()
    recent_logs = db.execute(
        """SELECT al.*, u.name AS admin_name FROM admin_logs al
           JOIN users u ON u.id = al.admin_id ORDER BY al.created_at DESC LIMIT 6"""
    ).fetchall()
    active_featured = db.execute(
        """SELECT l.id, l.title, l.featured_until, l.created_at, u.name AS donor_name
           FROM listings l JOIN users u ON u.id = l.donor_id
           WHERE l.is_featured = 1 AND l.status != 'removed'
           ORDER BY l.featured_until LIMIT 5"""
    ).fetchall()
    recent_disputes = db.execute(
        """SELECT d.*, reporter.name AS reporter_name, other.name AS other_name,
                  l.title AS listing_title
           FROM disputes d JOIN users reporter ON reporter.id = d.reporter_id
           LEFT JOIN users other ON other.id = d.other_user_id
           LEFT JOIN listings l ON l.id = d.listing_id
           WHERE d.status IN ('open', 'under_review')
           ORDER BY CASE d.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                    d.created_at DESC LIMIT 4"""
    ).fetchall()
    recent_concerns = db.execute(
        """SELECT sc.*, u.name AS user_name, u.email AS user_email
           FROM support_concerns sc JOIN users u ON u.id = sc.user_id
           WHERE sc.status IN ('open', 'in_progress')
           ORDER BY CASE sc.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                    sc.created_at DESC LIMIT 4"""
    ).fetchall()
    return render_template(
        "admin/overview.html",
        active_page="overview",
        stats=stats,
        days=days,
        max_activity=max_activity,
        category_counts=category_counts,
        max_category=max_category,
        recent_reports=recent_reports,
        pending_claims=pending_claims,
        recent_transactions=recent_transactions,
        recent_logs=recent_logs,
        active_featured=active_featured,
        recent_disputes=recent_disputes,
        recent_concerns=recent_concerns,
    )


@bp.route("/users")
def users():
    db = get_db()
    q = (request.args.get("q") or "").strip()
    status_filter = request.args.get("status") or "all"
    role_filter = request.args.get("role") or "all"
    where = ["1=1"]
    params: list = []
    if q:
        where.append("(u.name LIKE ? OR u.email LIKE ? OR p.city LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])
    if status_filter in {"active", "suspended"}:
        where.append("u.status = ?")
        params.append(status_filter)
    if role_filter in {"user", "admin"}:
        where.append("u.role = ?")
        params.append(role_filter)
    elif role_filter == "donor":
        where.append(
            "EXISTS (SELECT 1 FROM listings gl WHERE gl.donor_id = u.id AND gl.status != 'removed')"
        )
    elif role_filter == "recipient":
        where.append(
            "EXISTS (SELECT 1 FROM claims gc WHERE gc.claimant_id = u.id)"
        )
    rows = db.execute(
        """SELECT u.id, u.name, u.email, u.role, u.status, u.created_at, u.last_login,
                  u.email_verified, p.avatar_url, p.city, p.contact_number, p.verified,
                  (SELECT COUNT(*) FROM listings l WHERE l.donor_id = u.id AND l.status != 'removed') AS donation_count,
                  (SELECT COUNT(*) FROM claims c WHERE c.claimant_id = u.id) AS claim_count,
                  (SELECT COUNT(*) FROM reports r WHERE r.reported_user_id = u.id AND r.status = 'open') AS report_count
           FROM users u LEFT JOIN profiles p ON p.user_id = u.id
           WHERE """ + " AND ".join(where) + " ORDER BY u.created_at DESC",
        params,
    ).fetchall()
    stats = {
        "all": db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "active": db.execute("SELECT COUNT(*) FROM users WHERE status = 'active'").fetchone()[0],
        "suspended": db.execute("SELECT COUNT(*) FROM users WHERE status = 'suspended'").fetchone()[0],
        "verified": db.execute("SELECT COUNT(*) FROM users WHERE email_verified = 1").fetchone()[0],
        "donors": db.execute(
            """SELECT COUNT(DISTINCT donor_id) FROM listings WHERE status != 'removed'"""
        ).fetchone()[0],
        "recipients": db.execute(
            "SELECT COUNT(DISTINCT claimant_id) FROM claims"
        ).fetchone()[0],
    }
    return render_template(
        "admin/users.html",
        active_page="users",
        users=rows,
        stats=stats,
        q=q,
        status_filter=status_filter,
        role_filter=role_filter,
    )


@bp.route("/users/<int:user_id>")
def user_detail(user_id: int):
    db = get_db()
    user = db.execute(
        """SELECT u.*, p.avatar_url, p.contact_number, p.location, p.city, p.bio,
                  p.verified, p.member_since, p.latitude, p.longitude
           FROM users u LEFT JOIN profiles p ON p.user_id = u.id WHERE u.id = ?""",
        (user_id,),
    ).fetchone()
    if user is None:
        abort(404)
    stats = {
        "donations": db.execute(
            "SELECT COUNT(*) FROM listings WHERE donor_id = ? AND status != 'removed'", (user_id,)
        ).fetchone()[0],
        "gifts": db.execute(
            """SELECT COUNT(*) FROM claims c JOIN listings l ON l.id = c.listing_id
               WHERE l.donor_id = ? AND c.status = 'completed'""",
            (user_id,),
        ).fetchone()[0],
        "claims": db.execute(
            "SELECT COUNT(*) FROM claims WHERE claimant_id = ?", (user_id,)
        ).fetchone()[0],
        "received": db.execute(
            "SELECT COUNT(*) FROM claims WHERE claimant_id = ? AND status = 'completed'", (user_id,)
        ).fetchone()[0],
        "reports": db.execute(
            "SELECT COUNT(*) FROM reports WHERE reported_user_id = ? AND status = 'open'", (user_id,)
        ).fetchone()[0],
    }
    listings = db.execute(
        """SELECT l.*, c.name AS category_name FROM listings l
           JOIN categories c ON c.id = l.category_id
           WHERE l.donor_id = ? ORDER BY l.created_at DESC LIMIT 6""",
        (user_id,),
    ).fetchall()
    claims = db.execute(
        """SELECT c.*, l.title AS listing_title FROM claims c
           JOIN listings l ON l.id = c.listing_id
           WHERE c.claimant_id = ? ORDER BY c.created_at DESC LIMIT 8""",
        (user_id,),
    ).fetchall()
    reports = db.execute(
        """SELECT r.*, l.title AS listing_title FROM reports r
           LEFT JOIN listings l ON l.id = r.listing_id
           WHERE r.reported_user_id = ? ORDER BY r.created_at DESC LIMIT 6""",
        (user_id,),
    ).fetchall()
    return render_template(
        "admin/user_detail.html",
        active_page="users",
        user=user,
        stats=stats,
        listings=listings,
        claims=claims,
        reports=reports,
    )


@bp.route("/users/<int:user_id>/action", methods=["POST"])
def user_action(user_id: int):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)
    if user["id"] == g.user["id"]:
        flash("You cannot change your own administrative status here.", "error")
        return redirect(url_for("admin.user_detail", user_id=user_id))
    if user["role"] == "admin" and request.form.get("action") in {"suspend", "unverify"}:
        flash("Administrator accounts cannot be suspended from this action.", "error")
        return redirect(url_for("admin.user_detail", user_id=user_id))
    action = request.form.get("action") or ""
    if action == "suspend":
        db.execute("UPDATE users SET status = 'suspended' WHERE id = ?", (user_id,))
        notify(
            user_id, "announcement", "Account suspended",
            "Your Anti-Imbak account has been suspended. Contact hello@antiimbak.ph for a review.",
            None,
        )
        log_admin("Suspended user", "user", user_id, f"{user['name']} ({user['email']})")
        flash(f"{user['name']}'s account has been suspended.", "info")
    elif action == "reactivate":
        db.execute("UPDATE users SET status = 'active' WHERE id = ?", (user_id,))
        notify(
            user_id, "announcement", "Account reactivated",
            "Your account is active again. Welcome back to the community.",
            url_for("public.browse"),
        )
        log_admin("Reactivated user", "user", user_id, f"{user['name']} ({user['email']})")
        flash(f"{user['name']}'s account is active again.", "success")
    elif action in {"verify", "unverify"}:
        verified = 1 if action == "verify" else 0
        db.execute("UPDATE users SET email_verified = ? WHERE id = ?", (verified, user_id))
        db.execute("UPDATE profiles SET verified = ? WHERE user_id = ?", (verified, user_id))
        notify(
            user_id,
            "announcement",
            "Verification updated",
            "Your community verification status was updated by the Anti-Imbak team."
            if verified else "Your community verification status needs another review.",
            url_for("dashboard.settings"),
        )
        log_admin(
            "Verified user" if verified else "Unverified user", "user", user_id,
            f"Verification set to {bool(verified)} for {user['email']}.",
        )
        flash("Verification status updated.", "success")
    else:
        flash("That user action is not recognised.", "error")
    db.commit()
    return redirect(request.referrer or url_for("admin.users"))


@bp.route("/listings")
def listings():
    db = get_db()
    q = (request.args.get("q") or "").strip()
    status_filter = request.args.get("status") or "all"
    category_filter = request.args.get("category", type=int)
    featured_filter = request.args.get("featured") or "all"
    where = ["1=1"]
    params: list = []
    if q:
        like = f"%{q}%"
        where.append("(l.title LIKE ? OR u.name LIKE ? OR l.city LIKE ?)")
        params.extend([like, like, like])
    if status_filter in {"available", "reserved", "claimed", "unavailable", "removed"}:
        where.append("l.status = ?")
        params.append(status_filter)
    else:
        status_filter = "all"
    if category_filter:
        where.append("l.category_id = ?")
        params.append(category_filter)
    if featured_filter == "featured":
        where.append("l.is_featured = 1")
    elif featured_filter == "standard":
        where.append("l.is_featured = 0")
    rows = db.execute(
        """SELECT l.*, c.name AS category_name, c.icon AS category_icon,
                  u.name AS donor_name, u.email AS donor_email,
                  (SELECT image_url FROM listing_images li WHERE li.listing_id = l.id
                   ORDER BY li.sort_order, li.id LIMIT 1) AS primary_image,
                  (SELECT COUNT(*) FROM reports r WHERE r.listing_id = l.id AND r.status = 'open') AS open_reports,
                  (SELECT COUNT(*) FROM claims cl WHERE cl.listing_id = l.id AND cl.status = 'pending') AS pending_claims
           FROM listings l JOIN categories c ON c.id = l.category_id
           JOIN users u ON u.id = l.donor_id
           WHERE """ + " AND ".join(where) + """ ORDER BY
             CASE l.status WHEN 'available' THEN 0 WHEN 'reserved' THEN 1 WHEN 'claimed' THEN 2 ELSE 3 END,
             l.created_at DESC""",
        params,
    ).fetchall()
    categories = get_categories(include_inactive=True)
    stats = {
        "all": db.execute("SELECT COUNT(*) FROM listings").fetchone()[0],
        "available": db.execute("SELECT COUNT(*) FROM listings WHERE status = 'available'").fetchone()[0],
        "removed": db.execute("SELECT COUNT(*) FROM listings WHERE status = 'removed'").fetchone()[0],
        "featured": db.execute("SELECT COUNT(*) FROM listings WHERE is_featured = 1").fetchone()[0],
    }
    return render_template(
        "admin/listings.html",
        active_page="listings",
        listings=rows,
        categories=categories,
        stats=stats,
        q=q,
        status_filter=status_filter,
        category_filter=category_filter,
        featured_filter=featured_filter,
    )


@bp.route("/listings/<int:listing_id>/action", methods=["POST"])
def listing_action(listing_id: int):
    db = get_db()
    listing = db.execute(
        "SELECT l.*, u.name AS donor_name FROM listings l JOIN users u ON u.id = l.donor_id WHERE l.id = ?",
        (listing_id,),
    ).fetchone()
    if listing is None:
        abort(404)
    action = request.form.get("action") or ""
    now = stamp()
    if action == "remove":
        active_claims = db.execute(
            "SELECT * FROM claims WHERE listing_id = ? AND status IN ('pending', 'accepted')",
            (listing_id,),
        ).fetchall()
        for claim in active_claims:
            db.execute(
                "UPDATE claims SET status = 'cancelled', donor_note = 'Listing removed after an administrative review.', updated_at = ? WHERE id = ?",
                (now, claim["id"]),
            )
            notify(
                claim["claimant_id"], "listing_update", "A listing was removed",
                f"“{listing['title']}” was removed after an administrative review. Your active request was closed.",
                url_for("public.browse"),
            )
        db.execute(
            "UPDATE delivery_requests SET status = 'cancelled', updated_at = ? WHERE listing_id = ? AND status IN ('request_accepted','awaiting_dispatch','in_progress','arriving_soon')",
            (now, listing_id),
        )
        db.execute(
            "UPDATE listings SET status = 'removed', is_featured = 0, updated_at = ? WHERE id = ?",
            (now, listing_id),
        )
        notify(
            listing["donor_id"], "listing_update", "Your listing was removed",
            f"“{listing['title']}” was removed by the Anti-Imbak team. Please check the community guidelines or contact support.",
            url_for("dashboard.donations"),
        )
        log_admin("Removed listing", "listing", listing_id, f"{listing['title']} — {listing['donor_name']}")
        flash("Listing removed and active community requests were notified.", "info")
    elif action == "restore":
        db.execute(
            "UPDATE listings SET status = 'available', updated_at = ? WHERE id = ?",
            (now, listing_id),
        )
        notify(
            listing["donor_id"], "listing_update", "Your listing is live again",
            f"“{listing['title']}” has been restored to the marketplace.",
            url_for("public.listing_detail", listing_id=listing_id),
        )
        log_admin("Restored listing", "listing", listing_id, listing["title"])
        flash("Listing restored to the marketplace.", "success")
    elif action == "feature":
        ends = (utcnow() + timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            "UPDATE listings SET is_featured = 1, featured_until = ?, updated_at = ? WHERE id = ?",
            (ends, now, listing_id),
        )
        notify(
            listing["donor_id"], "listing_update", "An editorial feature was applied",
            f"“{listing['title']}” was given 14 days of editorial visibility by the Anti-Imbak team.",
            url_for("public.listing_detail", listing_id=listing_id),
        )
        log_admin("Featured listing", "listing", listing_id, "14-day editorial feature grant.")
        flash("Listing featured for 14 days (editorial grant — no charge).", "success")
    elif action == "unfeature":
        db.execute(
            "UPDATE listings SET is_featured = 0, updated_at = ? WHERE id = ?",
            (now, listing_id),
        )
        log_admin("Unfeatured listing", "listing", listing_id, listing["title"])
        flash("Listing returned to standard visibility.", "info")
    else:
        flash("That listing action is not recognised.", "error")
    db.commit()
    return redirect(request.referrer or url_for("admin.listings"))


@bp.route("/reports")
def reports():
    db = get_db()
    status_filter = request.args.get("status") or "open"
    sql = """SELECT r.*, l.title AS listing_title, l.status AS listing_status, l.id AS listing_id,
                    reporter.name AS reporter_name, reporter.email AS reporter_email,
                    reported.name AS reported_name, reported.email AS reported_email,
                    resolver.name AS resolver_name
             FROM reports r
             LEFT JOIN listings l ON l.id = r.listing_id
             JOIN users reporter ON reporter.id = r.reporter_id
             LEFT JOIN users reported ON reported.id = r.reported_user_id
             LEFT JOIN users resolver ON resolver.id = r.resolved_by
             WHERE 1=1"""
    params: list = []
    if status_filter != "all":
        sql += " AND r.status = ?"
        params.append(status_filter)
    sql += " ORDER BY CASE r.status WHEN 'open' THEN 0 ELSE 1 END, r.created_at DESC"
    rows = db.execute(sql, params).fetchall()
    stats = {
        "open": db.execute("SELECT COUNT(*) FROM reports WHERE status = 'open'").fetchone()[0],
        "resolved": db.execute("SELECT COUNT(*) FROM reports WHERE status = 'resolved'").fetchone()[0],
        "dismissed": db.execute("SELECT COUNT(*) FROM reports WHERE status = 'dismissed'").fetchone()[0],
        "all": db.execute("SELECT COUNT(*) FROM reports").fetchone()[0],
    }
    return render_template(
        "admin/reports.html",
        active_page="reports",
        reports=rows,
        stats=stats,
        status_filter=status_filter,
    )


@bp.route("/reports/<int:report_id>/resolve", methods=["POST"])
def resolve_report(report_id: int):
    db = get_db()
    report = db.execute(
        "SELECT * FROM reports WHERE id = ?", (report_id,)
    ).fetchone()
    if report is None:
        abort(404)
    action = request.form.get("action") or "resolve"
    note = (request.form.get("admin_note") or "").strip()
    if len(note) < 5:
        flash("Add a short administrative note before closing a report.", "error")
        return redirect(url_for("admin.reports"))
    status = "resolved" if action == "resolve" else "dismissed"
    db.execute(
        """UPDATE reports SET status = ?, admin_note = ?, resolved_by = ?, resolved_at = ?
           WHERE id = ?""",
        (status, note[:1000], g.user["id"], stamp(), report_id),
    )
    notify(
        report["reporter_id"], "announcement", f"Report {status}",
        "The safety team has reviewed your report. Thank you for helping keep Anti-Imbak safe.",
        url_for("dashboard.notifications"),
    )
    log_admin("Resolved report" if status == "resolved" else "Dismissed report", "report", report_id, note[:300])
    db.commit()
    flash(f"Report marked as {status}.", "success")
    return redirect(url_for("admin.reports"))


@bp.route("/disputes")
def disputes():
    db = get_db()
    status_filter = request.args.get("status") or "active"
    priority_filter = request.args.get("priority") or "all"
    q = (request.args.get("q") or "").strip()
    where = ["1=1"]
    params: list = []
    if status_filter == "active":
        where.append("d.status IN ('open', 'under_review')")
    elif status_filter in DISPUTE_STATUSES:
        where.append("d.status = ?")
        params.append(status_filter)
    else:
        status_filter = "all"
    if priority_filter in {"low", "medium", "high", "urgent"}:
        where.append("d.priority = ?")
        params.append(priority_filter)
    else:
        priority_filter = "all"
    if q:
        like = f"%{q}%"
        where.append(
            "(d.dispute_code LIKE ? OR d.summary LIKE ? OR d.category LIKE ? OR "
            "reporter.name LIKE ? OR other.name LIKE ? OR l.title LIKE ?)"
        )
        params.extend([like] * 6)
    rows = db.execute(
        """SELECT d.*, reporter.name AS reporter_name, reporter.email AS reporter_email,
                  other.name AS other_name, other.email AS other_email,
                  l.title AS listing_title, l.id AS listing_id,
                  assigned.name AS assigned_name,
                  (SELECT COUNT(*) FROM dispute_evidence e WHERE e.dispute_id = d.id) AS evidence_count,
                  (SELECT COUNT(*) FROM dispute_events ev WHERE ev.dispute_id = d.id) AS event_count
           FROM disputes d
           JOIN users reporter ON reporter.id = d.reporter_id
           LEFT JOIN users other ON other.id = d.other_user_id
           LEFT JOIN listings l ON l.id = d.listing_id
           LEFT JOIN users assigned ON assigned.id = d.assigned_admin_id
           WHERE """ + " AND ".join(where) + """
           ORDER BY CASE d.status WHEN 'open' THEN 0 WHEN 'under_review' THEN 1 WHEN 'resolved' THEN 2 ELSE 3 END,
                    CASE d.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                    d.created_at DESC""",
        params,
    ).fetchall()
    stats = {
        "all": db.execute("SELECT COUNT(*) FROM disputes").fetchone()[0],
        "open": db.execute("SELECT COUNT(*) FROM disputes WHERE status = 'open'").fetchone()[0],
        "under_review": db.execute("SELECT COUNT(*) FROM disputes WHERE status = 'under_review'").fetchone()[0],
        "urgent": db.execute(
            "SELECT COUNT(*) FROM disputes WHERE status IN ('open', 'under_review') AND priority = 'urgent'"
        ).fetchone()[0],
        "resolved": db.execute(
            "SELECT COUNT(*) FROM disputes WHERE status IN ('resolved', 'closed')"
        ).fetchone()[0],
    }
    stats["active"] = stats["open"] + stats["under_review"]
    return render_template(
        "admin/disputes.html",
        active_page="disputes",
        disputes=rows,
        stats=stats,
        status_filter=status_filter,
        priority_filter=priority_filter,
        q=q,
    )


@bp.route("/disputes/<int:dispute_id>")
def dispute_detail(dispute_id: int):
    db = get_db()
    dispute = db.execute(
        """SELECT d.*, reporter.name AS reporter_name, reporter.email AS reporter_email,
                  reporter.created_at AS reporter_joined, reporter.id AS reporter_id,
                  rp.avatar_url AS reporter_avatar, rp.verified AS reporter_verified,
                  other.name AS other_name, other.email AS other_email,
                  other.created_at AS other_joined, other.id AS other_id,
                  op.avatar_url AS other_avatar, op.verified AS other_verified,
                  l.title AS listing_title, l.id AS listing_id, l.status AS listing_status,
                  l.city AS listing_city, l.area AS listing_area,
                  assigned.name AS assigned_name, assigned.id AS assigned_id
           FROM disputes d
           JOIN users reporter ON reporter.id = d.reporter_id
           LEFT JOIN profiles rp ON rp.user_id = reporter.id
           LEFT JOIN users other ON other.id = d.other_user_id
           LEFT JOIN profiles op ON op.user_id = other.id
           LEFT JOIN listings l ON l.id = d.listing_id
           LEFT JOIN users assigned ON assigned.id = d.assigned_admin_id
           WHERE d.id = ?""",
        (dispute_id,),
    ).fetchone()
    if dispute is None:
        abort(404)
    evidence = db.execute(
        "SELECT * FROM dispute_evidence WHERE dispute_id = ? ORDER BY created_at, id",
        (dispute_id,),
    ).fetchall()
    events = db.execute(
        """SELECT ev.*, u.name AS actor_name FROM dispute_events ev
           LEFT JOIN users u ON u.id = ev.actor_id
           WHERE ev.dispute_id = ? ORDER BY ev.created_at, ev.id""",
        (dispute_id,),
    ).fetchall()
    return render_template(
        "admin/dispute_detail.html",
        active_page="disputes",
        dispute=dispute,
        evidence=evidence,
        events=events,
    )


@bp.route("/disputes/<int:dispute_id>/action", methods=["POST"])
def dispute_action(dispute_id: int):
    db = get_db()
    dispute = db.execute(
        "SELECT * FROM disputes WHERE id = ?", (dispute_id,)
    ).fetchone()
    if dispute is None:
        abort(404)
    action = (request.form.get("action") or "").strip()
    note = (request.form.get("note") or "").strip()[:1000]
    now = stamp()

    def add_event(event_type: str, body: str | None) -> None:
        db.execute(
            """INSERT INTO dispute_events (dispute_id, actor_id, event_type, note, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (dispute_id, g.user["id"], event_type, body, now),
        )

    if action == "assign":
        db.execute(
            "UPDATE disputes SET assigned_admin_id = ?, updated_at = ? WHERE id = ?",
            (g.user["id"], now, dispute_id),
        )
        add_event("assigned", f"Assigned to {g.user['name']} for casework.")
        log_admin("Assigned dispute", "dispute", dispute_id, f"{dispute['dispute_code']} → {g.user['name']}")
        flash("Dispute assigned to you.", "success")
    elif action == "note":
        if not note:
            note = (
                "Reviewed the case timeline and available evidence. Both members were asked "
                "to confirm the next safe handover step inside Anti-Imbak."
            )
        add_event("note", note)
        db.execute("UPDATE disputes SET updated_at = ? WHERE id = ?", (now, dispute_id))
        log_admin("Added dispute note", "dispute", dispute_id, note[:300])
        flash("Case note added to the dispute history.", "success")
    elif action == "status":
        new_status = (request.form.get("status") or "").strip()
        if new_status not in DISPUTE_STATUSES:
            flash("Choose a valid dispute status.", "error")
            return redirect(url_for("admin.dispute_detail", dispute_id=dispute_id))
        resolution = (request.form.get("resolution") or "").strip()[:2000]
        resolved_at = now if new_status in {"resolved", "closed"} else None
        db.execute(
            """UPDATE disputes SET status = ?, resolution = COALESCE(NULLIF(?, ''), resolution),
                      resolved_at = ?, updated_at = ? WHERE id = ?""",
            (new_status, resolution, resolved_at, now, dispute_id),
        )
        add_event("status", f"Status changed to {new_status.replace('_', ' ')}.")
        notify(
            dispute["reporter_id"],
            "announcement",
            "Dispute update",
            f"Case {dispute['dispute_code']} is now {new_status.replace('_', ' ')}.",
            url_for("dashboard.notifications"),
        )
        if dispute["other_user_id"]:
            notify(
                dispute["other_user_id"],
                "announcement",
                "Dispute update",
                f"Case {dispute['dispute_code']} is now {new_status.replace('_', ' ')}.",
                url_for("dashboard.notifications"),
            )
        log_admin("Updated dispute status", "dispute", dispute_id, f"{dispute['dispute_code']} → {new_status}")
        flash("Dispute status updated and both parties notified.", "success")
    elif action == "resolve":
        resolution = (request.form.get("resolution") or "").strip()[:2000]
        if not resolution:
            resolution = (
                "Reviewed the full case history and evidence with both members. A safe, "
                "public handover plan was agreed and each party was reminded to keep all "
                "coordination inside Anti-Imbak. No further action is needed."
            )
        db.execute(
            """UPDATE disputes SET status = 'resolved', resolution = ?, resolved_at = ?, updated_at = ?
               WHERE id = ?""",
            (resolution, now, now, dispute_id),
        )
        add_event("resolved", resolution)
        notify(
            dispute["reporter_id"],
            "announcement",
            "Dispute resolved",
            f"Case {dispute['dispute_code']} has been resolved. {resolution[:180]}",
            url_for("dashboard.notifications"),
        )
        if dispute["other_user_id"]:
            notify(
                dispute["other_user_id"],
                "announcement",
                "Dispute resolved",
                f"Case {dispute['dispute_code']} has been resolved. {resolution[:180]}",
                url_for("dashboard.notifications"),
            )
        log_admin("Resolved dispute", "dispute", dispute_id, resolution[:300])
        flash("Dispute resolved. Both parties were notified with the outcome.", "success")
    elif action == "reopen":
        db.execute(
            "UPDATE disputes SET status = 'open', resolved_at = NULL, updated_at = ? WHERE id = ?",
            (now, dispute_id),
        )
        add_event("reopened", note or "Case reopened for another review.")
        log_admin("Reopened dispute", "dispute", dispute_id, note[:300])
        flash("Dispute reopened for review.", "info")
    else:
        flash("That dispute action is not recognised.", "error")
    db.commit()
    return redirect(url_for("admin.dispute_detail", dispute_id=dispute_id))


@bp.route("/support")
def support():
    db = get_db()
    status_filter = request.args.get("status") or "active"
    priority_filter = request.args.get("priority") or "all"
    category_filter = request.args.get("category") or "all"
    q = (request.args.get("q") or "").strip()
    where = ["1=1"]
    params: list = []
    if status_filter == "active":
        where.append("sc.status IN ('open', 'in_progress')")
    elif status_filter in SUPPORT_STATUSES:
        where.append("sc.status = ?")
        params.append(status_filter)
    else:
        status_filter = "all"
    if priority_filter in {"low", "medium", "high", "urgent"}:
        where.append("sc.priority = ?")
        params.append(priority_filter)
    else:
        priority_filter = "all"
    if category_filter and category_filter != "all":
        where.append("sc.category = ?")
        params.append(category_filter)
    if q:
        like = f"%{q}%"
        where.append(
            "(sc.ticket_code LIKE ? OR sc.subject LIKE ? OR sc.message LIKE ? OR "
            "u.name LIKE ? OR u.email LIKE ?)"
        )
        params.extend([like] * 5)
    rows = db.execute(
        """SELECT sc.*, u.name AS user_name, u.email AS user_email,
                  p.avatar_url AS user_avatar, p.verified AS user_verified,
                  assigned.name AS assigned_name,
                  (SELECT COUNT(*) FROM support_messages sm WHERE sm.concern_id = sc.id) AS message_count,
                  (SELECT body FROM support_messages sm WHERE sm.concern_id = sc.id
                   ORDER BY sm.created_at DESC, sm.id DESC LIMIT 1) AS last_message,
                  (SELECT created_at FROM support_messages sm WHERE sm.concern_id = sc.id
                   ORDER BY sm.created_at DESC, sm.id DESC LIMIT 1) AS last_message_at
           FROM support_concerns sc JOIN users u ON u.id = sc.user_id
           LEFT JOIN profiles p ON p.user_id = u.id
           LEFT JOIN users assigned ON assigned.id = sc.assigned_admin_id
           WHERE """ + " AND ".join(where) + """
           ORDER BY CASE sc.status WHEN 'open' THEN 0 WHEN 'in_progress' THEN 1 WHEN 'resolved' THEN 2 ELSE 3 END,
                    CASE sc.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                    sc.created_at DESC""",
        params,
    ).fetchall()
    stats = {
        "all": db.execute("SELECT COUNT(*) FROM support_concerns").fetchone()[0],
        "open": db.execute("SELECT COUNT(*) FROM support_concerns WHERE status = 'open'").fetchone()[0],
        "in_progress": db.execute("SELECT COUNT(*) FROM support_concerns WHERE status = 'in_progress'").fetchone()[0],
        "urgent": db.execute(
            "SELECT COUNT(*) FROM support_concerns WHERE status IN ('open', 'in_progress') AND priority = 'urgent'"
        ).fetchone()[0],
        "resolved": db.execute(
            "SELECT COUNT(*) FROM support_concerns WHERE status IN ('resolved', 'closed')"
        ).fetchone()[0],
    }
    stats["active"] = stats["open"] + stats["in_progress"]
    categories = db.execute(
        "SELECT DISTINCT category FROM support_concerns ORDER BY category"
    ).fetchall()
    return render_template(
        "admin/support.html",
        active_page="support",
        concerns=rows,
        stats=stats,
        status_filter=status_filter,
        priority_filter=priority_filter,
        category_filter=category_filter,
        categories=[row["category"] for row in categories],
        q=q,
    )


@bp.route("/support/<int:concern_id>")
def support_detail(concern_id: int):
    db = get_db()
    concern = db.execute(
        """SELECT sc.*, u.name AS user_name, u.email AS user_email, u.created_at AS user_joined,
                  u.status AS user_status, p.avatar_url AS user_avatar, p.city AS user_city,
                  p.verified AS user_verified, assigned.name AS assigned_name
           FROM support_concerns sc JOIN users u ON u.id = sc.user_id
           LEFT JOIN profiles p ON p.user_id = u.id
           LEFT JOIN users assigned ON assigned.id = sc.assigned_admin_id
           WHERE sc.id = ?""",
        (concern_id,),
    ).fetchone()
    if concern is None:
        abort(404)
    messages = db.execute(
        """SELECT sm.*, u.name AS sender_name, p.avatar_url AS sender_avatar
           FROM support_messages sm
           LEFT JOIN users u ON u.id = sm.sender_id
           LEFT JOIN profiles p ON p.user_id = sm.sender_id
           WHERE sm.concern_id = ? ORDER BY sm.created_at, sm.id""",
        (concern_id,),
    ).fetchall()
    return render_template(
        "admin/support_detail.html",
        active_page="support",
        concern=concern,
        messages=messages,
    )


@bp.route("/support/<int:concern_id>/action", methods=["POST"])
def support_action(concern_id: int):
    db = get_db()
    concern = db.execute(
        "SELECT * FROM support_concerns WHERE id = ?", (concern_id,)
    ).fetchone()
    if concern is None:
        abort(404)
    action = (request.form.get("action") or "").strip()
    now = stamp()
    if action == "reply":
        body = (request.form.get("body") or "").strip()[:3000]
        if not body:
            body = (
                "Thanks for reaching out. I’ve reviewed your concern and shared the next "
                "step in this thread. Please reply here if anything else comes up — we’ll "
                "keep this ticket open until you’re comfortable."
            )
        db.execute(
            """INSERT INTO support_messages (concern_id, sender_id, sender_label, body, is_admin, created_at)
               VALUES (?, ?, 'Support team', ?, 1, ?)""",
            (concern_id, g.user["id"], body, now),
        )
        db.execute(
            """UPDATE support_concerns SET status = CASE WHEN status = 'open' THEN 'in_progress' ELSE status END,
                      assigned_admin_id = COALESCE(assigned_admin_id, ?), updated_at = ? WHERE id = ?""",
            (g.user["id"], now, concern_id),
        )
        notify(
            concern["user_id"],
            "announcement",
            "Support replied to your concern",
            f"{concern['ticket_code']}: {body[:180]}",
            url_for("dashboard.notifications"),
        )
        log_admin("Replied to user concern", "support_concern", concern_id, f"{concern['ticket_code']} — {body[:250]}")
        flash("Reply sent to the member and the concern is now in progress.", "success")
    elif action == "status":
        new_status = (request.form.get("status") or "").strip()
        if new_status not in SUPPORT_STATUSES:
            flash("Choose a valid support status.", "error")
            return redirect(url_for("admin.support_detail", concern_id=concern_id))
        resolution = (request.form.get("resolution") or "").strip()[:2000]
        resolved_at = now if new_status in {"resolved", "closed"} else None
        db.execute(
            """UPDATE support_concerns SET status = ?, resolution = COALESCE(NULLIF(?, ''), resolution),
                      resolved_at = ?, updated_at = ? WHERE id = ?""",
            (new_status, resolution, resolved_at, now, concern_id),
        )
        notify(
            concern["user_id"],
            "announcement",
            "Concern update",
            f"{concern['ticket_code']} is now {new_status.replace('_', ' ')}.",
            url_for("dashboard.notifications"),
        )
        log_admin("Updated concern status", "support_concern", concern_id, f"{concern['ticket_code']} → {new_status}")
        flash("Support concern status updated and the member notified.", "success")
    elif action == "assign":
        db.execute(
            "UPDATE support_concerns SET assigned_admin_id = ?, updated_at = ? WHERE id = ?",
            (g.user["id"], now, concern_id),
        )
        log_admin("Assigned user concern", "support_concern", concern_id, concern["ticket_code"])
        flash("Concern assigned to you.", "success")
    elif action == "reopen":
        db.execute(
            "UPDATE support_concerns SET status = 'open', resolved_at = NULL, updated_at = ? WHERE id = ?",
            (now, concern_id),
        )
        log_admin("Reopened user concern", "support_concern", concern_id, concern["ticket_code"])
        flash("Concern reopened.", "info")
    else:
        flash("That support action is not recognised.", "error")
    db.commit()
    return redirect(url_for("admin.support_detail", concern_id=concern_id))


@bp.route("/activity")
def activity():
    db = get_db()
    q = (request.args.get("q") or "").strip()
    admin_filter = request.args.get("admin", type=int)
    target_filter = (request.args.get("target") or "all").strip()
    page = max(1, request.args.get("page", 1, type=int) or 1)
    per_page = 25
    where = ["1=1"]
    params: list = []
    if q:
        like = f"%{q}%"
        where.append("(al.action LIKE ? OR al.details LIKE ?)")
        params.extend([like, like])
    if admin_filter:
        where.append("al.admin_id = ?")
        params.append(admin_filter)
    if target_filter != "all":
        where.append("al.target_type = ?")
        params.append(target_filter)
    total = db.execute(
        "SELECT COUNT(*) FROM admin_logs al WHERE " + " AND ".join(where), params
    ).fetchone()[0]
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)
    logs = db.execute(
        """SELECT al.*, u.name AS admin_name, u.email AS admin_email
           FROM admin_logs al JOIN users u ON u.id = al.admin_id
           WHERE """ + " AND ".join(where) + """
           ORDER BY al.created_at DESC, al.id DESC LIMIT ? OFFSET ?""",
        params + [per_page, (page - 1) * per_page],
    ).fetchall()
    admins = db.execute(
        """SELECT DISTINCT u.id, u.name FROM admin_logs al
           JOIN users u ON u.id = al.admin_id ORDER BY u.name"""
    ).fetchall()
    target_types = [
        row["target_type"]
        for row in db.execute(
            "SELECT DISTINCT target_type FROM admin_logs ORDER BY target_type"
        ).fetchall()
    ]
    stats = {
        "total": total,
        "today": db.execute(
            "SELECT COUNT(*) FROM admin_logs WHERE date(created_at) = ?",
            (utcnow().date().isoformat(),),
        ).fetchone()[0],
        "week": db.execute(
            "SELECT COUNT(*) FROM admin_logs WHERE created_at >= ?",
            (stamp(utcnow() - timedelta(days=7)),),
        ).fetchone()[0],
        "admins": len(admins),
    }
    return render_template(
        "admin/activity.html",
        active_page="activity",
        logs=logs,
        admins=admins,
        target_types=target_types,
        stats=stats,
        q=q,
        admin_filter=admin_filter,
        target_filter=target_filter,
        page=page,
        pages=pages,
        total=total,
    )


@bp.route("/revenue")
def revenue():
    db = get_db()
    type_filter = request.args.get("type") or "all"
    q = (request.args.get("q") or "").strip()
    where = ["1=1"]
    params: list = []
    if type_filter in {"featured", "delivery", "advertisement"}:
        where.append("t.type = ?")
        params.append(type_filter)
    if q:
        where.append("(t.description LIKE ? OR u.name LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like])
    transactions = db.execute(
        """SELECT t.*, u.name AS user_name FROM transactions t
           LEFT JOIN users u ON u.id = t.user_id
           WHERE """ + " AND ".join(where) + """ ORDER BY t.created_at DESC LIMIT 150""",
        params,
    ).fetchall()
    summary = {
        "featured": _sum_transactions("featured"),
        "delivery_fees": _sum_transactions("delivery"),
        "advertisement": _sum_transactions("advertisement"),
    }
    summary["total_platform_revenue"] = round(
        summary["featured"] + summary["advertisement"], 2
    )
    type_totals = {
        row["type"]: row["total"]
        for row in db.execute(
            "SELECT type, COALESCE(SUM(amount), 0) AS total FROM transactions WHERE status='completed' GROUP BY type"
        ).fetchall()
    }
    deliveries = db.execute(
        """SELECT d.*, dp.name AS partner_name, l.title AS listing_title,
                  requester.name AS requester_name
           FROM delivery_requests d
           LEFT JOIN delivery_partners dp ON dp.id = d.partner_id
           JOIN listings l ON l.id = d.listing_id
           JOIN users requester ON requester.id = d.requester_id
           ORDER BY d.created_at DESC LIMIT 12"""
    ).fetchall()
    return render_template(
        "admin/revenue.html",
        active_page="revenue",
        transactions=transactions,
        summary=summary,
        type_totals=type_totals,
        deliveries=deliveries,
        type_filter=type_filter,
        q=q,
    )


@bp.route("/revenue.csv")
def revenue_csv():
    db = get_db()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Transaction ID", "Date", "Type", "User", "Description", "Amount (PHP)",
        "Revenue treatment", "Status",
    ])
    rows = db.execute(
        """SELECT t.*, u.name AS user_name FROM transactions t
           LEFT JOIN users u ON u.id = t.user_id ORDER BY t.created_at DESC"""
    ).fetchall()
    for row in rows:
        treatment = (
            "Passed to delivery partner"
            if row["type"] == "delivery"
            else "Platform revenue"
        )
        writer.writerow([
            row["id"], row["created_at"], row["type"], row["user_name"] or "Advertising client",
            row["description"], f"{row['amount']:.2f}", treatment, row["status"],
        ])
    output = Response(buffer.getvalue(), mimetype="text/csv")
    output.headers["Content-Disposition"] = "attachment; filename=anti-imbak-revenue.csv"
    return output


@bp.route("/content")
def content():
    db = get_db()
    ads = db.execute(
        """SELECT a.*, p.name AS package_name, c.name AS category_name
           FROM advertisements a LEFT JOIN ad_packages p ON p.id = a.package_id
           LEFT JOIN categories c ON c.id = a.category_id
           ORDER BY a.status, a.created_at DESC"""
    ).fetchall()
    packages = db.execute("SELECT * FROM ad_packages ORDER BY price DESC").fetchall()
    categories = get_categories(include_inactive=True)
    tips = db.execute("SELECT * FROM safety_tips ORDER BY sort_order, id").fetchall()
    inquiries = db.execute(
        """SELECT i.*, p.name AS package_name FROM ad_inquiries i
           LEFT JOIN ad_packages p ON p.id = i.package_id
           ORDER BY CASE i.status WHEN 'new' THEN 0 WHEN 'contacted' THEN 1 ELSE 2 END,
                    i.created_at DESC"""
    ).fetchall()
    stats = {
        "active_ads": db.execute("SELECT COUNT(*) FROM advertisements WHERE status = 'active'").fetchone()[0],
        "new_inquiries": db.execute("SELECT COUNT(*) FROM ad_inquiries WHERE status = 'new'").fetchone()[0],
        "categories": db.execute("SELECT COUNT(*) FROM categories WHERE active = 1").fetchone()[0],
        "tips": db.execute("SELECT COUNT(*) FROM safety_tips WHERE active = 1").fetchone()[0],
    }
    return render_template(
        "admin/content.html",
        active_page="content",
        ads=ads,
        packages=packages,
        categories=categories,
        tips=tips,
        inquiries=inquiries,
        stats=stats,
        ad_images=ALLOWED_AD_IMAGES,
        category_icons=CATEGORY_ICONS,
    )


@bp.route("/ads", methods=["POST"])
def create_ad():
    db = get_db()
    advertiser_name = (request.form.get("advertiser_name") or "").strip()
    business_type = (request.form.get("business_type") or "").strip()
    title = (request.form.get("title") or "").strip()
    body = (request.form.get("body") or "").strip()
    cta_label = (request.form.get("cta_label") or "Learn more").strip()
    cta_url = (request.form.get("cta_url") or "").strip() or url_for("public.advertise")
    image_key = request.form.get("image") or "none"
    placement = request.form.get("placement") or ""
    category_id = request.form.get("category_id", type=int)
    package_id = request.form.get("package_id", type=int)
    days = request.form.get("days", type=int) or 30
    record_revenue = request.form.get("record_revenue") == "on"
    errors = []
    if len(advertiser_name) < 2:
        errors.append("Add the advertiser's name.")
    if len(business_type) < 2:
        errors.append("Add the business type.")
    if len(title) < 5:
        errors.append("Add an advertisement headline.")
    if placement not in {"home_banner", "browse_sidebar", "category"}:
        errors.append("Choose a valid placement.")
    if image_key not in ALLOWED_AD_IMAGES:
        errors.append("Choose a valid advertising image.")
    if not is_safe_redirect_url(cta_url):
        errors.append("The call-to-action must be a valid internal or https link.")
    package = db.execute("SELECT * FROM ad_packages WHERE id = ?", (package_id,)).fetchone()
    if package is None:
        errors.append("Choose an advertising package.")
    if not 1 <= days <= 365:
        errors.append("The campaign length must be between 1 and 365 days.")
    if placement == "category":
        selected_category = db.execute("SELECT id FROM categories WHERE id = ?", (category_id,)).fetchone()
        if selected_category is None:
            errors.append("Choose a category for a category placement.")
    if errors:
        for error in errors:
            flash(error, "error")
        return redirect(url_for("admin.content"))
    starts = utcnow()
    ends = starts + timedelta(days=days)
    cur = db.execute(
        """INSERT INTO advertisements
           (advertiser_name, business_type, title, body, cta_label, cta_url, image_url, placement,
            category_id, package_id, status, starts_at, ends_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
        (
            advertiser_name, business_type, title, body, cta_label, cta_url,
            ALLOWED_AD_IMAGES[image_key] or None, placement,
            category_id if placement == "category" else None, package["id"],
            stamp(starts), stamp(ends),
        ),
    )
    if record_revenue:
        db.execute(
            """INSERT INTO transactions
               (user_id, type, reference_type, reference_id, amount, platform_fee, provider_payout,
                payment_method, description, status)
               VALUES (NULL, 'advertisement', 'advertisement', ?, ?, ?, 0, 'Advertising invoice', ?, 'completed')""",
            (
                cur.lastrowid, package["price"], package["price"],
                f"{advertiser_name} — {package['name']} (admin-created campaign)",
            ),
        )
    log_admin("Created advertisement", "advertisement", cur.lastrowid, f"{advertiser_name} — {title}")
    db.commit()
    flash("Advertisement created and placed. Paid campaigns are clearly labelled to visitors.", "success")
    return redirect(url_for("admin.content"))


@bp.route("/ads/<int:ad_id>/status", methods=["POST"])
def ad_status(ad_id: int):
    db = get_db()
    ad = db.execute("SELECT * FROM advertisements WHERE id = ?", (ad_id,)).fetchone()
    if ad is None:
        abort(404)
    status = request.form.get("status") or ""
    if status not in {"active", "paused", "expired"}:
        flash("Choose a valid advertisement status.", "error")
        return redirect(url_for("admin.content"))
    db.execute("UPDATE advertisements SET status = ? WHERE id = ?", (status, ad_id))
    log_admin("Updated advertisement status", "advertisement", ad_id, f"{ad['advertiser_name']} -> {status}")
    db.commit()
    flash(f"Advertisement marked as {status}.", "success")
    return redirect(url_for("admin.content"))


@bp.route("/packages/<int:package_id>/toggle", methods=["POST"])
def package_toggle(package_id: int):
    db = get_db()
    package = db.execute("SELECT * FROM ad_packages WHERE id = ?", (package_id,)).fetchone()
    if package is None:
        abort(404)
    new_state = 0 if package["active"] else 1
    db.execute("UPDATE ad_packages SET active = ? WHERE id = ?", (new_state, package_id))
    log_admin("Updated ad package", "ad_package", package_id, f"{package['name']} active={bool(new_state)}")
    db.commit()
    flash("Advertising package availability updated.", "success")
    return redirect(url_for("admin.content"))


@bp.route("/categories", methods=["POST"])
def create_category():
    db = get_db()
    name = (request.form.get("name") or "").strip()
    icon = (request.form.get("icon") or "box").strip()
    description = (request.form.get("description") or "").strip()
    if len(name) < 2 or len(name) > 60:
        flash("Category names need between 2 and 60 characters.", "error")
        return redirect(url_for("admin.content"))
    if icon not in CATEGORY_ICONS:
        flash("Choose a valid category icon.", "error")
        return redirect(url_for("admin.content"))
    slug = slugify(name)
    if db.execute("SELECT 1 FROM categories WHERE slug = ? OR name = ?", (slug, name)).fetchone():
        flash("A category with that name already exists.", "error")
        return redirect(url_for("admin.content"))
    max_sort = db.execute("SELECT COALESCE(MAX(sort_order), 0) FROM categories").fetchone()[0]
    cur = db.execute(
        "INSERT INTO categories (name, slug, icon, description, sort_order) VALUES (?, ?, ?, ?, ?)",
        (name, slug, icon, description or None, max_sort + 1),
    )
    log_admin("Created category", "category", cur.lastrowid, name)
    db.commit()
    flash("Donation category added. It is now visible in the marketplace.", "success")
    return redirect(url_for("admin.content") + "#categories")


@bp.route("/categories/<int:category_id>/toggle", methods=["POST"])
def toggle_category(category_id: int):
    db = get_db()
    category = db.execute("SELECT * FROM categories WHERE id = ?", (category_id,)).fetchone()
    if category is None:
        abort(404)
    new_state = 0 if category["active"] else 1
    db.execute("UPDATE categories SET active = ? WHERE id = ?", (new_state, category_id))
    log_admin("Updated category", "category", category_id, f"{category['name']} active={bool(new_state)}")
    db.commit()
    flash("Category visibility updated.", "success")
    return redirect(url_for("admin.content") + "#categories")


@bp.route("/safety", methods=["POST"])
def update_safety():
    raw = (request.form.get("tips") or "").strip()
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) < 3 or len(lines) > 12:
        flash("Provide between 3 and 12 safety tips, one per line.", "error")
        return redirect(url_for("admin.content") + "#safety")
    if any(len(line) > 300 for line in lines):
        flash("Each safety tip must stay under 300 characters.", "error")
        return redirect(url_for("admin.content") + "#safety")
    db = get_db()
    db.execute("DELETE FROM safety_tips")
    for index, line in enumerate(lines, start=1):
        db.execute(
            "INSERT INTO safety_tips (text, sort_order, active) VALUES (?, ?, 1)",
            (line, index),
        )
    log_admin("Updated safety guidelines", "content", None, f"{len(lines)} tips published.")
    db.commit()
    flash("Safety guidelines updated for the whole marketplace.", "success")
    return redirect(url_for("admin.content") + "#safety")


@bp.route("/announcement", methods=["POST"])
def announcement():
    title = (request.form.get("title") or "").strip()
    message = (request.form.get("message") or "").strip()
    if len(title) < 4 or len(title) > 100:
        flash("Announcement titles need 4–100 characters.", "error")
        return redirect(url_for("admin.content") + "#announcement")
    if len(message) < 10 or len(message) > 600:
        flash("Announcement messages need 10–600 characters.", "error")
        return redirect(url_for("admin.content") + "#announcement")
    db = get_db()
    users = db.execute("SELECT id FROM users WHERE status = 'active'").fetchall()
    for user in users:
        notify(
            user["id"], "announcement", title, message,
            url_for("dashboard.notifications"),
        )
    log_admin("Broadcast announcement", "announcement", None, title)
    db.commit()
    flash(f"Announcement sent to {len(users)} active members.", "success")
    return redirect(url_for("admin.content") + "#announcement")


@bp.route("/inquiries/<int:inquiry_id>/status", methods=["POST"])
def inquiry_status(inquiry_id: int):
    db = get_db()
    inquiry = db.execute("SELECT * FROM ad_inquiries WHERE id = ?", (inquiry_id,)).fetchone()
    if inquiry is None:
        abort(404)
    status = request.form.get("status") or ""
    if status not in {"new", "contacted", "closed"}:
        flash("Choose a valid inquiry status.", "error")
        return redirect(url_for("admin.content") + "#inquiries")
    db.execute("UPDATE ad_inquiries SET status = ? WHERE id = ?", (status, inquiry_id))
    log_admin("Updated advertising inquiry", "ad_inquiry", inquiry_id, f"{inquiry['business_name']} -> {status}")
    db.commit()
    flash("Inquiry status updated.", "success")
    return redirect(url_for("admin.content") + "#inquiries")
