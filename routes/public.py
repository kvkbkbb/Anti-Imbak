"""Public-facing routes: landing page, marketplace, listings and content."""
from __future__ import annotations

import math

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from services import (
    CITIES,
    CONDITIONS,
    LISTING_CARD_SQL,
    REPORT_REASONS,
    attach_listing_state,
    delivery_quote,
    get_active_ad,
    get_categories,
    get_db,
    get_listing_detail,
    get_my_saved_ids,
    get_or_create_conversation,
    login_required,
    new_tracking_code,
    notify,
    notify_admins,
    record_ad_click,
    reference_coordinates,
    safe_next,
    stamp,
)

bp = Blueprint("public", __name__)


@bp.route("/")
def index():
    db = get_db()
    featured_rows = db.execute(
        LISTING_CARD_SQL
        + """ WHERE l.status = 'available' AND l.is_featured = 1
              ORDER BY l.featured_until DESC, l.created_at DESC LIMIT 3"""
    ).fetchall()
    featured = attach_listing_state([dict(row) for row in featured_rows])
    featured_ids = [item["id"] for item in featured]

    recent_rows = db.execute(
        LISTING_CARD_SQL
        + """ WHERE l.status = 'available'
              ORDER BY l.created_at DESC LIMIT 12"""
    ).fetchall()
    recent_pool = attach_listing_state([dict(row) for row in recent_rows])
    recent = [item for item in recent_pool if item["id"] not in featured_ids][:6]
    if len(recent) < 6:
        recent += [item for item in recent_pool if item not in recent][: 6 - len(recent)]

    categories = get_categories()
    banner_ad = get_active_ad("home_banner")
    stats = {
        "members": db.execute("SELECT COUNT(*) FROM users WHERE status = 'active'").fetchone()[0],
        "items": db.execute("SELECT COUNT(*) FROM listings WHERE status != 'removed'").fetchone()[0],
        "gifts": db.execute("SELECT COUNT(*) FROM claims WHERE status = 'completed'").fetchone()[0],
        "cities": db.execute(
            "SELECT COUNT(DISTINCT city) FROM listings WHERE status != 'removed'"
        ).fetchone()[0],
    }
    stats["diverted_kg"] = round(stats["gifts"] * 4.2, 1)
    stats["co2_kg"] = round(stats["gifts"] * 8.4, 1)

    hero_listing = featured[0] if featured else (recent[0] if recent else None)
    if hero_listing and hero_listing.get("primary_image"):
        hero_image = hero_listing["primary_image"]
    else:
        hero_image = "/static/img/laptop.jpg"

    reference = reference_coordinates()
    nearby_pool = attach_listing_state(
        [
            dict(row)
            for row in db.execute(
                LISTING_CARD_SQL
                + """ WHERE l.status = 'available'
                      ORDER BY l.is_featured DESC, l.created_at DESC LIMIT 40"""
            ).fetchall()
        ],
        reference,
    )
    nearby_pool.sort(key=lambda item: (item.get("distance_km", 0), not item["is_featured"]))
    nearby = nearby_pool[:3]
    nearby_city = (g.user.get("city") if g.get("user") else None) or "Quezon City"

    db.commit()
    return render_template(
        "index.html",
        featured=featured,
        recent=recent,
        nearby=nearby,
        nearby_city=nearby_city,
        categories=categories,
        banner_ad=banner_ad,
        stats=stats,
        hero_listing=hero_listing,
        hero_image=hero_image,
    )


@bp.route("/browse")
def browse():
    db = get_db()
    q = (request.args.get("q") or "").strip()[:120]
    category_slug = (request.args.get("category") or "").strip()
    location = (request.args.get("location") or "").strip()
    condition = (request.args.get("condition") or "").strip()
    availability = (request.args.get("availability") or "available").strip()
    sort = (request.args.get("sort") or "featured").strip()
    page = max(request.args.get("page", type=int) or 1, 1)
    per_page = 12

    categories = get_categories()
    category_lookup = {row["slug"]: row for row in categories}
    selected_category = category_lookup.get(category_slug)

    where = ["l.status != 'removed'"]
    params: list = []
    if selected_category:
        where.append("l.category_id = ?")
        params.append(selected_category["id"])
    if location in CITIES:
        where.append("l.city = ?")
        params.append(location)
    else:
        location = ""
    if condition in CONDITIONS:
        where.append("l.condition = ?")
        params.append(condition)
    else:
        condition = ""
    if availability in {"available", "reserved", "claimed", "unavailable"}:
        where.append("l.status = ?")
        params.append(availability)
    elif availability != "all":
        availability = "available"
        where.append("l.status = 'available'")
    else:
        availability = "all"
    if q:
        like = f"%{q}%"
        where.append(
            "(l.title LIKE ? OR l.description LIKE ? OR c.name LIKE ? OR l.city LIKE ? OR l.area LIKE ?)"
        )
        params.extend([like] * 5)
    if sort not in {"featured", "newest", "nearest"}:
        sort = "featured"

    query = LISTING_CARD_SQL + " WHERE " + " AND ".join(where) + " ORDER BY l.created_at DESC"
    rows = db.execute(query, params).fetchall()
    listings = attach_listing_state([dict(row) for row in rows])
    reference = reference_coordinates(location if location else None)
    if sort == "nearest":
        for listing in listings:
            listing["distance_km"] = round(
                _haversine(reference, (listing["latitude"], listing["longitude"])), 1
            )
        listings.sort(key=lambda item: (item["distance_km"], not item["is_featured"], item["created_at"]))
    elif sort == "featured":
        listings.sort(
            key=lambda item: (not bool(item["is_featured"]), item.get("featured_until") or "", item["created_at"]),
            reverse=True,
        )
    else:
        listings.sort(key=lambda item: item["created_at"], reverse=True)

    total = len(listings)
    total_pages = max(math.ceil(total / per_page), 1)
    page = min(page, total_pages)
    start = (page - 1) * per_page
    page_listings = listings[start:start + per_page]

    def page_url(number: int) -> str:
        args = request.args.to_dict()
        args["page"] = number
        return url_for("public.browse", **args)

    sidebar_ad = get_active_ad("browse_sidebar")
    category_ad = get_active_ad("category", selected_category["id"]) if selected_category else None
    active_filter_count = sum(bool(value) for value in [
        q,
        selected_category,
        location,
        condition,
        availability not in ("available", ""),
        sort not in ("featured", ""),
    ])

    near_label = location or (g.user.get("city") if g.get("user") else None) or "Quezon City"

    db.commit()
    return render_template(
        "marketplace.html",
        listings=page_listings,
        categories=categories,
        selected_category=selected_category,
        q=q,
        location=location,
        condition=condition,
        availability=availability,
        sort=sort,
        total=total,
        page=page,
        total_pages=total_pages,
        page_url=page_url,
        active_filter_count=active_filter_count,
        sidebar_ad=sidebar_ad,
        category_ad=category_ad,
        near_label=near_label,
    )


def _haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


@bp.route("/listings/<int:listing_id>")
def listing_detail(listing_id: int):
    db = get_db()
    listing = get_listing_detail(listing_id)
    if listing is None:
        abort(404)
    db.execute("UPDATE listings SET views = views + 1 WHERE id = ?", (listing_id,))
    listing["views"] = (listing["views"] or 0) + 1
    listing["is_saved"] = listing_id in get_my_saved_ids()

    my_claim = None
    has_open_report = False
    if g.get("user"):
        row = db.execute(
            "SELECT * FROM claims WHERE listing_id = ? AND claimant_id = ?",
            (listing_id, g.user["id"]),
        ).fetchone()
        my_claim = dict(row) if row else None
        has_open_report = bool(
            db.execute(
                "SELECT 1 FROM reports WHERE listing_id = ? AND reporter_id = ? AND status = 'open'",
                (listing_id, g.user["id"]),
            ).fetchone()
        )

    images = listing["images"] or [
        {"image_url": "/static/img/boxes.svg", "alt_text": listing["title"]}
    ]
    related = attach_listing_state(
        [
            dict(row)
            for row in db.execute(
                LISTING_CARD_SQL
                + """ WHERE l.category_id = ? AND l.id != ? AND l.status = 'available'
                      ORDER BY l.is_featured DESC, l.created_at DESC LIMIT 3""",
                (listing["category_id"], listing_id),
            ).fetchall()
        ]
    )
    category_ad = get_active_ad("category", listing["category_id"])
    safety_tips = [
        row["text"]
        for row in db.execute(
            "SELECT text FROM safety_tips WHERE active = 1 ORDER BY sort_order, id"
        ).fetchall()
    ]
    can_claim = bool(
        g.get("user")
        and g.user["id"] != listing["donor_id"]
        and listing["status"] == "available"
        and (my_claim is None or my_claim["status"] in {"rejected", "cancelled"})
    )
    default_quote = delivery_quote(listing, g.get("user"))
    conversation = None
    if g.get("user") and g.user["id"] != listing["donor_id"]:
        conversation = db.execute(
            """SELECT id FROM conversations
               WHERE listing_id = ? AND donor_id = ? AND recipient_id = ?""",
            (listing_id, listing["donor_id"], g.user["id"]),
        ).fetchone()
    db.commit()
    return render_template(
        "listing_detail.html",
        listing=listing,
        images=images,
        my_claim=my_claim,
        can_claim=can_claim,
        has_open_report=has_open_report,
        related=related,
        category_ad=category_ad,
        safety_tips=safety_tips,
        report_reasons=REPORT_REASONS,
        default_quote=default_quote,
        conversation=conversation,
    )


@bp.route("/members/<int:user_id>")
def member_profile(user_id: int):
    db = get_db()
    user = db.execute(
        """SELECT u.id, u.name, u.role, u.status, u.created_at, u.email_verified,
                  p.avatar_url, p.city, p.bio, p.verified, p.member_since
           FROM users u LEFT JOIN profiles p ON p.user_id = u.id
           WHERE u.id = ?""",
        (user_id,),
    ).fetchone()
    if user is None:
        abort(404)
    stats = {
        "listings": db.execute(
            "SELECT COUNT(*) FROM listings WHERE donor_id = ? AND status != 'removed'", (user_id,)
        ).fetchone()[0],
        "available": db.execute(
            "SELECT COUNT(*) FROM listings WHERE donor_id = ? AND status = 'available'", (user_id,)
        ).fetchone()[0],
        "gifts": db.execute(
            """SELECT COUNT(*) FROM claims c JOIN listings l ON l.id = c.listing_id
               WHERE l.donor_id = ? AND c.status = 'completed'""",
            (user_id,),
        ).fetchone()[0],
        "received": db.execute(
            "SELECT COUNT(*) FROM claims WHERE claimant_id = ? AND status = 'completed'", (user_id,)
        ).fetchone()[0],
    }
    listings = attach_listing_state(
        [
            dict(row)
            for row in db.execute(
                LISTING_CARD_SQL
                + """ WHERE l.donor_id = ? AND l.status = 'available'
                      ORDER BY l.is_featured DESC, l.created_at DESC LIMIT 6""",
                (user_id,),
            ).fetchall()
        ]
    )
    gifts = [
        dict(row)
        for row in db.execute(
            """SELECT l.id, l.title, l.city, l.area, c.updated_at AS completed_at,
                      cat.name AS category_name,
                      (SELECT image_url FROM listing_images li WHERE li.listing_id = l.id
                       ORDER BY li.sort_order, li.id LIMIT 1) AS primary_image
               FROM claims c JOIN listings l ON l.id = c.listing_id
               JOIN categories cat ON cat.id = l.category_id
               WHERE l.donor_id = ? AND c.status = 'completed'
               ORDER BY c.updated_at DESC LIMIT 4""",
            (user_id,),
        ).fetchall()
    ]
    return render_template(
        "member_profile.html",
        member=user,
        stats=stats,
        listings=listings,
        gifts=gifts,
    )


@bp.route("/listings/<int:listing_id>/save", methods=["POST"])
@login_required
def toggle_save(listing_id: int):
    db = get_db()
    listing = db.execute(
        "SELECT id, title, status FROM listings WHERE id = ?", (listing_id,)
    ).fetchone()
    if listing is None or listing["status"] == "removed":
        abort(404)
    existing = db.execute(
        "SELECT 1 FROM saved_listings WHERE user_id = ? AND listing_id = ?",
        (g.user["id"], listing_id),
    ).fetchone()
    if existing:
        db.execute(
            "DELETE FROM saved_listings WHERE user_id = ? AND listing_id = ?",
            (g.user["id"], listing_id),
        )
        flash("Removed from your saved listings.", "info")
    else:
        db.execute(
            "INSERT INTO saved_listings (user_id, listing_id) VALUES (?, ?)",
            (g.user["id"], listing_id),
        )
        flash("Saved for later. Find it under Saved Items in your account.", "success")
    db.commit()
    return redirect(safe_next(request.form.get("next"), url_for("public.listing_detail", listing_id=listing_id)))


@bp.route("/listings/<int:listing_id>/claim", methods=["POST"])
@login_required
def claim_listing(listing_id: int):
    db = get_db()
    listing = get_listing_detail(listing_id)
    if listing is None:
        abort(404)
    if listing["donor_id"] == g.user["id"]:
        flash("Your own listing is already yours. No claim needed.", "info")
        return redirect(url_for("public.listing_detail", listing_id=listing_id))
    if listing["status"] != "available":
        flash("This item is no longer available to claim right now.", "error")
        return redirect(url_for("public.listing_detail", listing_id=listing_id))

    message = (request.form.get("message") or "").strip()
    method = request.form.get("receive_method") or "delivery"
    delivery_address = (request.form.get("delivery_address") or "").strip()
    safety_ack = request.form.get("safety_ack") == "on"
    errors = []
    if len(message) < 30:
        errors.append("Please share at least 30 characters about why this item would help you.")
    if len(message) > 1500:
        errors.append("Please keep your message under 1,500 characters.")
    if method not in {"pickup", "delivery"}:
        errors.append("Choose Partnered Delivery or Self Pickup.")
    method = "delivery" if method == "delivery" else "pickup"
    if not safety_ack:
        errors.append("Please confirm that you have read the safe handover reminders.")
    if method == "delivery" and len(delivery_address) < 10:
        errors.append("Enter a complete delivery address so the fee can be calculated.")
    if errors:
        for error in errors:
            flash(error, "error")
        return redirect(url_for("public.listing_detail", listing_id=listing_id) + "#claim")

    existing = db.execute(
        "SELECT * FROM claims WHERE listing_id = ? AND claimant_id = ?",
        (listing_id, g.user["id"]),
    ).fetchone()
    if existing and existing["status"] in {"pending", "accepted", "completed"}:
        flash("You already have an active claim for this item.", "info")
        return redirect(url_for("public.listing_detail", listing_id=listing_id))

    quote = delivery_quote(listing, g.user) if method == "delivery" else None
    now = stamp()
    if existing:
        db.execute(
            """UPDATE claims SET message = ?, receive_method = ?, delivery_address = ?,
                      status = 'pending', donor_note = NULL, handover_confirmed = 0, updated_at = ?
               WHERE id = ?""",
            (message, method, delivery_address or None, now, existing["id"]),
        )
        claim_id = existing["id"]
        db.execute("DELETE FROM delivery_requests WHERE claim_id = ?", (claim_id,))
    else:
        cur = db.execute(
            """INSERT INTO claims
               (listing_id, claimant_id, message, receive_method, delivery_address,
                status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (listing_id, g.user["id"], message, method, delivery_address or None, now, now),
        )
        claim_id = cur.lastrowid

    if quote:
        db.execute(
            """INSERT INTO delivery_requests
               (claim_id, listing_id, requester_id, partner_id, pickup_address, dropoff_address,
                distance_km, fee, status, tracking_code, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'request_accepted', ?, ?, ?)""",
            (claim_id, listing_id, g.user["id"], quote["partner_id"],
             f"{listing['area']}, {listing['city']}", delivery_address,
             quote["distance_km"], quote["fee"], new_tracking_code(), now, now),
        )

    conversation_id = get_or_create_conversation(
        listing["donor_id"], g.user["id"], listing_id, claim_id, message
    )
    notify(
        listing["donor_id"],
        "claim_request",
        "New claim request",
        f"{g.user['name']} would love to give “{listing['title']}” a new purpose.",
        url_for("dashboard.incoming_claims"),
    )
    notify(
        listing["donor_id"],
        "message",
        "New message from a Recipient",
        f"{g.user['name']} sent a note about “{listing['title']}”.",
        url_for("dashboard.messages", conversation=conversation_id),
    )
    notify(
        g.user["id"],
        "claim_request",
        "Request submitted",
        f"Your request for “{listing['title']}” is now with the Donor. We will let you know when there is an update.",
        url_for("dashboard.my_claims"),
    )
    db.commit()
    flash(
        "Your claim request is on its way. Partnered Delivery is selected and the total fee is shown on your request."
        if method == "delivery"
        else "Your claim request is on its way. You chose Self Pickup, so no delivery fee applies.",
        "success",
    )
    return redirect(url_for("dashboard.my_claims"))


@bp.route("/listings/<int:listing_id>/report", methods=["POST"])
@login_required
def report_listing(listing_id: int):
    db = get_db()
    listing = db.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
    if listing is None or listing["status"] == "removed":
        abort(404)
    if listing["donor_id"] == g.user["id"]:
        flash("You cannot report your own listing.", "info")
        return redirect(url_for("public.listing_detail", listing_id=listing_id))
    reason = (request.form.get("reason") or "").strip()
    details = (request.form.get("details") or "").strip()
    if reason not in REPORT_REASONS:
        flash("Choose a report reason so the safety team can review it.", "error")
        return redirect(url_for("public.listing_detail", listing_id=listing_id))
    if len(details) < 10:
        flash("Add a little more detail so the team can investigate.", "error")
        return redirect(url_for("public.listing_detail", listing_id=listing_id))
    db.execute(
        """INSERT INTO reports (reporter_id, listing_id, reported_user_id, reason, details, status)
           VALUES (?, ?, ?, ?, ?, 'open')""",
        (g.user["id"], listing_id, listing["donor_id"], reason, details[:2000]),
    )
    notify_admins(
        "New listing report",
        f"A community member reported “{listing['title']}” for: {reason}.",
        url_for("admin.reports"),
    )
    db.commit()
    flash("Thank you for looking out for the community. Our safety team will review this report.", "success")
    return redirect(url_for("public.listing_detail", listing_id=listing_id))


@bp.route("/how-it-works")
def how_it_works():
    return render_template("how_it_works.html")


@bp.route("/about")
def about():
    db = get_db()
    stats = {
        "members": db.execute("SELECT COUNT(*) FROM users WHERE status = 'active'").fetchone()[0],
        "gifts": db.execute("SELECT COUNT(*) FROM claims WHERE status = 'completed'").fetchone()[0],
        "listings": db.execute("SELECT COUNT(*) FROM listings WHERE status != 'removed'").fetchone()[0],
    }
    return render_template("about.html", stats=stats)


@bp.route("/safety")
def safety():
    tips = get_db().execute(
        "SELECT * FROM safety_tips WHERE active = 1 ORDER BY sort_order, id"
    ).fetchall()
    return render_template("safety.html", tips=tips)


@bp.route("/advertise", methods=["GET", "POST"])
def advertise():
    db = get_db()
    packages = db.execute(
        "SELECT * FROM ad_packages WHERE active = 1 ORDER BY price DESC"
    ).fetchall()
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        business_name = (request.form.get("business_name") or "").strip()
        business_type = (request.form.get("business_type") or "").strip()
        package_id = request.form.get("package_id", type=int)
        message = (request.form.get("message") or "").strip()
        errors = []
        if len(name) < 2:
            errors.append("Please add your name.")
        if "@" not in email or "." not in email.split("@")[-1]:
            errors.append("Please add a valid email address.")
        if len(business_name) < 2:
            errors.append("Please add your business name.")
        if not business_type:
            errors.append("Tell us what kind of local business you run.")
        valid_package = db.execute(
            "SELECT id FROM ad_packages WHERE id = ? AND active = 1", (package_id,)
        ).fetchone()
        if not valid_package:
            errors.append("Choose an advertising package.")
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            db.execute(
                """INSERT INTO ad_inquiries
                   (name, email, business_name, business_type, package_id, message, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'new')""",
                (name, email, business_name, business_type, valid_package["id"], message[:1500]),
            )
            notify_admins(
                "New advertising inquiry",
                f"{business_name} would like to know more about advertising with Anti-Imbak.",
                url_for("admin.content"),
            )
            db.commit()
            flash("Your inquiry is in. Our partnerships team will reply by email within two business days.", "success")
            return redirect(url_for("public.advertise") + "?sent=1")
    return render_template("advertise.html", packages=packages)


@bp.route("/sponsored/<int:ad_id>")
def sponsored(ad_id: int):
    db = get_db()
    ad = db.execute(
        """SELECT a.*, p.name AS package_name, p.duration_days
           FROM advertisements a LEFT JOIN ad_packages p ON p.id = a.package_id
           WHERE a.id = ?""",
        (ad_id,),
    ).fetchone()
    if ad is None:
        abort(404)
    db.execute("UPDATE advertisements SET impressions = impressions + 1 WHERE id = ?", (ad_id,))
    db.commit()
    return render_template("sponsored.html", ad=dict(ad))


@bp.route("/ad/<int:ad_id>/visit")
def ad_visit(ad_id: int):
    db = get_db()
    ad = db.execute(
        "SELECT * FROM advertisements WHERE id = ? AND status = 'active'", (ad_id,)
    ).fetchone()
    if not ad:
        abort(404)
    record_ad_click(ad_id)
    db.commit()
    target = ad["cta_url"] or url_for("public.advertise")
    # Allow same-site links and explicit http(s) destinations only.
    from services import is_safe_redirect_url

    return redirect(target if is_safe_redirect_url(target) else url_for("public.advertise"))


@bp.route("/privacy")
def privacy():
    return render_template("legal.html", page="privacy")


@bp.route("/terms")
def terms():
    return render_template("legal.html", page="terms")


@bp.route("/health")
def health():
    return {"status": "ok", "service": "anti-imbak"}
