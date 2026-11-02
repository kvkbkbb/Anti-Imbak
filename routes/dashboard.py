"""Member account flows: listings, requests, messages, delivery and settings."""
from __future__ import annotations

from datetime import timedelta

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from db import LOCATION_COORDS, haversine_km
from services import (
    CITIES,
    CONDITIONS,
    DELIVERY_STEPS,
    DELIVERY_STATUS_LABELS,
    FEATURED_PACKAGES,
    ITEM_SIZES,
    LISTING_CARD_SQL,
    MAX_IMAGES_PER_LISTING,
    attach_listing_state,
    conversation_list,
    conversation_messages,
    current_perspective,
    delivery_quote,
    find_conversation,
    get_categories,
    get_db,
    get_listing_detail,
    get_or_create_conversation,
    login_required,
    long_date,
    mark_conversation_read,
    new_tracking_code,
    notify,
    reference_coordinates,
    safe_next,
    save_avatar,
    save_image_uploads,
    stamp,
    utcnow,
)

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

RECEIVING_IMAGES = {
    "laptop": {"label": "Laptop", "url": "/static/img/laptop-used.jpg"},
    "chair": {"label": "Chair", "url": "/static/img/chair-used.jpg"},
    "sofa": {"label": "Sofa", "url": "/static/img/sofa-worn.jpg"},
    "books": {"label": "Books", "url": "/static/img/books-used.jpg"},
    "clothing": {"label": "Clothing", "url": "/static/img/clothes-bundle.jpg"},
    "appliance": {"label": "Appliance", "url": "/static/img/washer-used.jpg"},
    "toys": {"label": "Toys", "url": "/static/img/toys-used.jpg"},
    "bike": {"label": "Bicycle", "url": "/static/img/bike-used.jpg"},
    "kitchen": {"label": "Kitchenware", "url": "/static/img/kitchen-used.jpg"},
    "other": {"label": "Other item", "url": "/static/img/lamp-used.jpg"},
}

ACTIVE_DELIVERY_STATUSES = {"request_accepted", "awaiting_dispatch", "in_progress", "arriving_soon"}


def _owned_listing(listing_id: int, include_removed: bool = False) -> dict:
    listing = get_listing_detail(listing_id, allow_removed=True)
    if listing is None or listing["donor_id"] != g.user["id"]:
        abort(404)
    if listing["status"] == "removed" and not include_removed:
        abort(404)
    return listing


@bp.route("/")
@login_required
def index():
    """Send each signed-in member to their role-appropriate starting page."""
    if current_perspective() == "admin" or g.user["role"] == "admin":
        return redirect(url_for("admin.overview"))
    if current_perspective() == "recipient":
        return redirect(url_for("dashboard.my_claims"))
    return redirect(url_for("dashboard.donations"))


@bp.route("/donations")
@login_required
def donations():
    db = get_db()
    status_filter = request.args.get("status") or "all"
    sql = """SELECT l.*, c.name AS category_name, c.icon AS category_icon,
                    (SELECT image_url FROM listing_images li WHERE li.listing_id = l.id
                     ORDER BY li.sort_order, li.id LIMIT 1) AS primary_image,
                    (SELECT COUNT(*) FROM claims cl WHERE cl.listing_id = l.id) AS claim_count,
                    (SELECT COUNT(*) FROM claims cl WHERE cl.listing_id = l.id AND cl.status = 'pending') AS pending_claims,
                    (SELECT COUNT(*) FROM saved_listings sl WHERE sl.listing_id = l.id) AS save_count
             FROM listings l JOIN categories c ON c.id = l.category_id
             WHERE l.donor_id = ? AND l.status != 'removed'"""
    params = [g.user["id"]]
    if status_filter in {"available", "reserved", "claimed", "unavailable"}:
        sql += " AND l.status = ?"
        params.append(status_filter)
    sql += " ORDER BY l.created_at DESC"
    items = [dict(row) for row in db.execute(sql, params).fetchall()]
    for item in items:
        item["interested"] = [
            dict(row)
            for row in db.execute(
                """SELECT c.id AS claim_id, c.status, c.created_at, c.receive_method,
                          u.id AS claimant_id, u.name AS claimant_name,
                          p.avatar_url AS claimant_avatar
                   FROM claims c JOIN users u ON u.id = c.claimant_id
                   LEFT JOIN profiles p ON p.user_id = u.id
                   WHERE c.listing_id = ? AND c.status IN ('pending', 'accepted')
                   ORDER BY c.created_at DESC LIMIT 3""",
                (item["id"],),
            ).fetchall()
        ]
    counts = {
        row["status"]: row["total"]
        for row in db.execute(
            """SELECT status, COUNT(*) AS total FROM listings
               WHERE donor_id = ? AND status != 'removed' GROUP BY status""",
            (g.user["id"],),
        ).fetchall()
    }
    counts["all"] = sum(counts.values())
    return render_template(
        "dashboard/donations.html",
        active_page="donations",
        donations=items,
        counts=counts,
        status_filter=status_filter,
    )


@bp.route("/browse")
@login_required
def browse():
    return redirect(url_for("public.browse"))


def _listing_form_data(form, files, existing_count: int = 0) -> tuple[dict, dict, list]:
    data = {
        "title": (form.get("title") or "").strip(),
        "description": (form.get("description") or "").strip(),
        "category_id": form.get("category_id", type=int),
        "condition": (form.get("condition") or "").strip(),
        "item_size": (form.get("item_size") or "medium").strip(),
        "city": (form.get("city") or "").strip(),
        "area": (form.get("area") or "").strip(),
        "sample_image": (form.get("sample_image") or "").strip(),
    }
    errors: dict[str, str] = {}
    if len(data["title"]) < 5 or len(data["title"]) > 120:
        errors["title"] = "Use a clear item name between 5 and 120 characters."
    if len(data["description"]) < 40:
        errors["description"] = "Share at least 40 characters about the item's history and condition."
    if len(data["description"]) > 2000:
        errors["description"] = "Please keep the description under 2,000 characters."
    db = get_db()
    category = db.execute(
        "SELECT id FROM categories WHERE id = ? AND active = 1", (data["category_id"],)
    ).fetchone()
    if category is None:
        errors["category_id"] = "Choose a category."
    if data["condition"] not in CONDITIONS:
        errors["condition"] = "Choose the item's condition."
    if data["item_size"] not in ITEM_SIZES:
        errors["item_size"] = "Choose a size so the delivery fee can be estimated."
    if data["city"] not in CITIES:
        errors["city"] = "Choose a city."
    if len(data["area"]) < 2 or len(data["area"]) > 100:
        errors["area"] = "Add the neighbourhood or barangay."
    if data["sample_image"] and data["sample_image"] not in RECEIVING_IMAGES:
        errors["images"] = "Choose a valid photo."
    upload_files = [f for f in files if f and f.filename]
    selected_sample = 1 if data["sample_image"] else 0
    if existing_count == 0 and not upload_files and not selected_sample:
        errors["images"] = "Add at least one photo of the actual item."
    if existing_count + len(upload_files) + selected_sample > MAX_IMAGES_PER_LISTING:
        errors["images"] = f"Listings can have up to {MAX_IMAGES_PER_LISTING} photos."
    return data, errors, upload_files


def _listing_form_is_blank(form, files) -> bool:
    fields = [
        "title", "description", "category_id", "condition", "item_size", "city", "area",
        "sample_image",
    ]
    if any((form.get(field) or "").strip() for field in fields):
        return False
    return not any(f and f.filename for f in files)


def _create_listing(data: dict, images: list[str]) -> int:
    db = get_db()
    now = stamp()
    latitude, longitude = listing_coordinates_for(data["city"], data["title"] + data["area"])
    cur = db.execute(
        """INSERT INTO listings
           (donor_id, category_id, title, description, condition, item_size, city, area,
            latitude, longitude, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'available', ?, ?)""",
        (
            g.user["id"], data["category_id"], data["title"], data["description"],
            data["condition"], data["item_size"], data["city"], data["area"],
            latitude, longitude, now, now,
        ),
    )
    for index, image_url in enumerate(images):
        db.execute(
            "INSERT INTO listing_images (listing_id, image_url, alt_text, sort_order) VALUES (?, ?, ?, ?)",
            (cur.lastrowid, image_url, f"{data['title']} — photo {index + 1}", index),
        )
    notify(
        g.user["id"],
        "listing_update",
        "Your listing is live",
        f"“{data['title']}” is now visible to the Anti-Imbak community.",
        url_for("public.listing_detail", listing_id=cur.lastrowid),
    )
    db.commit()
    return cur.lastrowid


def listing_coordinates_for(city: str, seed_text: str) -> tuple[float, float]:
    from services import listing_coordinates

    return listing_coordinates(city, seed_text)


def _render_listing_form(mode: str, listing, form, errors, categories, selected_category):
    return render_template(
        "dashboard/listing_form.html",
        active_page="donations",
        mode=mode,
        listing=listing,
        form=form,
        errors=errors,
        categories=categories,
        receiving_images=RECEIVING_IMAGES,
        selected_category=selected_category,
    )


@bp.route("/donations/new", methods=["GET", "POST"])
@login_required
def new_donation():
    categories = get_categories()
    if request.method == "POST":
        data, errors, upload_files = _listing_form_data(request.form, request.files, 0)
        if errors:
            flash("Please check the highlighted fields before publishing.", "error")
            return _render_listing_form("create", None, request.form, errors, categories, None), 400
        saved_files, image_error = save_image_uploads(upload_files)
        if image_error:
            errors["images"] = image_error
            flash(image_error, "error")
            return _render_listing_form("create", None, request.form, errors, categories, None), 400
        images = [RECEIVING_IMAGES[data["sample_image"]]["url"]] if data["sample_image"] else []
        images.extend(saved_files)
        if not images:
            flash("Please add at least one photo.", "error")
            return redirect(url_for("dashboard.new_donation"))
        listing_id = _create_listing(data, images)
        flash("Your listing is live. Interested Recipients can now send a request.", "success")
        return redirect(url_for("dashboard.boost", listing_id=listing_id, new=1))
    return _render_listing_form("create", None, {}, {}, categories, None)


@bp.route("/donations/<int:listing_id>/edit", methods=["GET", "POST"])
@login_required
def edit_donation(listing_id: int):
    listing = _owned_listing(listing_id)
    categories = get_categories()
    if request.method == "POST":
        data, errors, upload_files = _listing_form_data(
            request.form, request.files, len(listing["images"])
        )
        if errors:
            flash("Please check the highlighted fields before saving.", "error")
            return _render_listing_form(
                "edit", listing, request.form, errors, categories, listing["category_id"]
            ), 400
        saved_files, image_error = save_image_uploads(upload_files)
        if image_error:
            errors["images"] = image_error
            flash(image_error, "error")
            return _render_listing_form(
                "edit", listing, request.form, errors, categories, listing["category_id"]
            ), 400
        images = []
        if data["sample_image"]:
            images.append(RECEIVING_IMAGES[data["sample_image"]]["url"])
        images.extend(saved_files)
        if not listing["images"] and not images:
            flash("This listing needs at least one photo.", "error")
            return redirect(url_for("dashboard.edit_donation", listing_id=listing_id))
        db = get_db()
        db.execute(
            """UPDATE listings SET category_id = ?, title = ?, description = ?, condition = ?,
                      item_size = ?, city = ?, area = ?, latitude = ?, longitude = ?, updated_at = ?
               WHERE id = ? AND donor_id = ?""",
            (
                data["category_id"], data["title"], data["description"], data["condition"],
                data["item_size"], data["city"], data["area"],
                *listing_coordinates_for(data["city"], data["title"] + data["area"]),
                stamp(), listing_id, g.user["id"],
            ),
        )
        sort_start = len(listing["images"])
        for index, image_url in enumerate(images):
            db.execute(
                "INSERT INTO listing_images (listing_id, image_url, alt_text, sort_order) VALUES (?, ?, ?, ?)",
                (listing_id, image_url, f"{data['title']} — photo {sort_start + index + 1}", sort_start + index),
            )
        active_claimants = db.execute(
            """SELECT DISTINCT claimant_id FROM claims
               WHERE listing_id = ? AND status IN ('pending', 'accepted')""",
            (listing_id,),
        ).fetchall()
        for claimant in active_claimants:
            notify(
                claimant["claimant_id"],
                "listing_update",
                "A listing you are interested in was updated",
                f"The details for “{data['title']}” have been refreshed. Review the latest information.",
                url_for("public.listing_detail", listing_id=listing_id),
            )
        db.commit()
        flash("Your listing has been updated.", "success")
        return redirect(url_for("dashboard.donations"))
    form = {
        "title": listing["title"],
        "description": listing["description"],
        "category_id": listing["category_id"],
        "condition": listing["condition"],
        "item_size": listing["item_size"],
        "city": listing["city"],
        "area": listing["area"],
        "sample_image": "",
    }
    return _render_listing_form(
        "edit", listing, form, {}, categories, listing["category_id"]
    )


@bp.route("/donations/<int:listing_id>/delete", methods=["POST"])
@login_required
def delete_donation(listing_id: int):
    listing = _owned_listing(listing_id)
    db = get_db()
    accepted = db.execute(
        "SELECT COUNT(*) FROM claims WHERE listing_id = ? AND status = 'accepted'", (listing_id,)
    ).fetchone()[0]
    if accepted:
        flash("Complete or resolve the accepted request before removing this listing.", "error")
        return redirect(url_for("dashboard.donations"))
    pending = db.execute(
        "SELECT c.*, u.name AS claimant_name FROM claims c JOIN users u ON u.id = c.claimant_id "
        "WHERE c.listing_id = ? AND c.status = 'pending'",
        (listing_id,),
    ).fetchall()
    for claim in pending:
        db.execute(
            "UPDATE claims SET status = 'cancelled', donor_note = 'Listing removed by the Donor.', updated_at = ? WHERE id = ?",
            (stamp(), claim["id"]),
        )
        notify(
            claim["claimant_id"],
            "listing_update",
            "A listing was removed",
            f"“{listing['title']}” is no longer available. Your request was closed and no action is needed.",
            url_for("public.browse"),
        )
    db.execute("DELETE FROM saved_listings WHERE listing_id = ?", (listing_id,))
    db.execute(
        "UPDATE listings SET status = 'removed', is_featured = 0, updated_at = ? WHERE id = ?",
        (stamp(), listing_id),
    )
    db.commit()
    flash("Your listing has been removed from the marketplace.", "info")
    return redirect(url_for("dashboard.donations"))


@bp.route("/donations/<int:listing_id>/status", methods=["POST"])
@login_required
def update_donation_status(listing_id: int):
    listing = _owned_listing(listing_id)
    action = request.form.get("action") or ""
    db = get_db()
    if listing["status"] in {"reserved", "claimed"}:
        flash("This item is in an active handover, so its status is locked for now.", "error")
        return redirect(url_for("dashboard.donations"))
    if action == "mark_unavailable":
        pending = db.execute(
            "SELECT id, claimant_id FROM claims WHERE listing_id = ? AND status = 'pending'",
            (listing_id,),
        ).fetchall()
        for claim in pending:
            db.execute(
                "UPDATE claims SET status = 'cancelled', donor_note = 'Donor marked the item unavailable.', updated_at = ? WHERE id = ?",
                (stamp(), claim["id"]),
            )
            notify(
                claim["claimant_id"], "listing_update", "A listing changed availability",
                f"“{listing['title']}” was marked unavailable by the Donor.",
                url_for("public.browse"),
            )
        db.execute(
            "UPDATE listings SET status = 'unavailable', is_featured = 0, updated_at = ? WHERE id = ?",
            (stamp(), listing_id),
        )
        flash("Your listing is now marked unavailable.", "info")
    elif action == "mark_available":
        db.execute(
            "UPDATE listings SET status = 'available', updated_at = ? WHERE id = ?",
            (stamp(), listing_id),
        )
        flash("Your listing is available to the community again.", "success")
    else:
        flash("That status change is not available.", "error")
    db.commit()
    return redirect(url_for("dashboard.donations"))


@bp.route("/donations/<int:listing_id>/boost", methods=["GET", "POST"])
@login_required
def boost(listing_id: int):
    listing = _owned_listing(listing_id)
    if request.method == "POST":
        package_key = (request.form.get("package") or "").strip()
        if package_key not in FEATURED_PACKAGES:
            flash("Choose a valid promotion package.", "error")
            return redirect(url_for("dashboard.boost", listing_id=listing_id))
        if listing["status"] in {"claimed", "unavailable", "removed"}:
            flash("This listing is not eligible for a promotion right now.", "error")
            return redirect(url_for("dashboard.donations"))
        if package_key == "standard":
            flash("Your listing will stay on the standard free plan.", "info")
            return redirect(url_for("dashboard.donations"))
        if request.form.get("promotion_ack") != "on":
            flash("Please confirm the promotion record before activating it.", "error")
            return redirect(url_for("dashboard.boost", listing_id=listing_id))
        package = FEATURED_PACKAGES[package_key]
        db = get_db()
        now = utcnow()
        current_until = None
        if listing["is_featured"] and listing["featured_until"]:
            from services import parse_stamp

            current_until = parse_stamp(listing["featured_until"])
        start = now
        base = current_until if current_until and current_until > now else now
        end = base + timedelta(days=package["days"])
        starts_at = stamp(start)
        ends_at = end.strftime("%Y-%m-%d %H:%M:%S")
        transaction = db.execute(
            """INSERT INTO transactions
               (user_id, type, reference_type, reference_id, amount, platform_fee, provider_payout,
                payment_method, description, status)
               VALUES (?, 'featured', 'listing', ?, ?, ?, 0, ?, ?, 'completed')""",
            (
                g.user["id"], listing_id, package["fee"], package["fee"],
                "Promotion record",
                f"{package['name']} promotion — {listing['title']}",
            ),
        )
        db.execute(
            """INSERT INTO featured_listings
               (listing_id, donor_id, package, amount, starts_at, ends_at, transaction_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (listing_id, g.user["id"], package_key, package["fee"], starts_at, ends_at, transaction.lastrowid),
        )
        db.execute(
            """UPDATE listings SET is_featured = 1, featured_until = ?, updated_at = ? WHERE id = ?""",
            (ends_at, stamp(), listing_id),
        )
        notify(
            g.user["id"],
            "listing_update",
            "Your listing is boosted",
            f"“{listing['title']}” is now featured until {long_date(ends_at)}.",
            url_for("public.listing_detail", listing_id=listing_id),
        )
        db.commit()
        flash("Your promotion is active. The record is available in Account Settings.", "success")
        return redirect(url_for("dashboard.donations"))
    return render_template(
        "dashboard/boost.html",
        active_page="donations",
        listing=listing,
        packages=FEATURED_PACKAGES,
    )


@bp.route("/claims")
@login_required
def incoming_claims():
    db = get_db()
    status_filter = request.args.get("status") or "pending"
    sql = """SELECT c.*, l.title AS listing_title, l.id AS listing_id, l.status AS listing_status,
                    l.city AS listing_city, l.area AS listing_area, l.donor_id,
                    u.name AS claimant_name, u.created_at AS claimant_joined,
                    p.avatar_url AS claimant_avatar, p.verified AS claimant_verified,
                    (SELECT image_url FROM listing_images li WHERE li.listing_id = l.id
                     ORDER BY li.sort_order, li.id LIMIT 1) AS listing_image,
                    d.id AS delivery_id, d.status AS delivery_status, d.fee AS delivery_fee,
                    d.tracking_code, dp.name AS partner_name
             FROM claims c JOIN listings l ON l.id = c.listing_id
             JOIN users u ON u.id = c.claimant_id
             LEFT JOIN profiles p ON p.user_id = u.id
             LEFT JOIN delivery_requests d ON d.claim_id = c.id
             LEFT JOIN delivery_partners dp ON dp.id = d.partner_id
             WHERE l.donor_id = ?"""
    params: list = [g.user["id"]]
    if status_filter != "all":
        sql += " AND c.status = ?"
        params.append(status_filter)
    sql += " ORDER BY CASE c.status WHEN 'pending' THEN 0 WHEN 'accepted' THEN 1 ELSE 2 END, c.created_at DESC"
    claims = [dict(row) for row in db.execute(sql, params).fetchall()]
    for claim in claims:
        claim["conversation_id"] = _conversation_id_for(claim["listing_id"], claim["donor_id"], claim["claimant_id"])
    counts = {
        row["status"]: row["total"]
        for row in db.execute(
            """SELECT c.status, COUNT(*) AS total FROM claims c JOIN listings l ON l.id = c.listing_id
               WHERE l.donor_id = ? GROUP BY c.status""",
            (g.user["id"],),
        ).fetchall()
    }
    counts["all"] = sum(counts.values())
    return render_template(
        "dashboard/claims_incoming.html",
        active_page="claims",
        claims=claims,
        counts=counts,
        status_filter=status_filter,
    )


def _conversation_id_for(listing_id, donor_id, recipient_id) -> int | None:
    row = get_db().execute(
        """SELECT id FROM conversations
           WHERE listing_id = ? AND donor_id = ? AND recipient_id = ?""",
        (listing_id, donor_id, recipient_id),
    ).fetchone()
    return row["id"] if row else None


@bp.route("/claims/<int:claim_id>")
@login_required
def claim_detail(claim_id: int):
    db = get_db()
    claim = db.execute(
        """SELECT c.*, l.title AS listing_title, l.id AS listing_id, l.status AS listing_status,
                  l.city AS listing_city, l.area AS listing_area, l.item_size,
                  l.condition AS listing_condition, l.donor_id,
                  claimant.name AS claimant_name, claimant.email AS claimant_email,
                  claimant.created_at AS claimant_joined,
                  cp.avatar_url AS claimant_avatar, cp.city AS claimant_city,
                  cp.bio AS claimant_bio, cp.verified AS claimant_verified,
                  CASE WHEN c.status IN ('accepted', 'completed') THEN cp.contact_number END AS claimant_contact,
                  donor.name AS donor_name, donor.email AS donor_email,
                  donor.created_at AS donor_joined,
                  dp.avatar_url AS donor_avatar, dp.city AS donor_city,
                  dp.bio AS donor_bio, dp.verified AS donor_verified,
                  CASE WHEN c.status IN ('accepted', 'completed') THEN dp.contact_number END AS donor_contact,
                  (SELECT image_url FROM listing_images li WHERE li.listing_id = l.id
                   ORDER BY li.sort_order, li.id LIMIT 1) AS listing_image,
                  d.id AS delivery_id, d.status AS delivery_status, d.fee AS delivery_fee,
                  d.tracking_code, d.distance_km AS delivery_distance, d.dropoff_address,
                  d.pickup_address, partner.name AS partner_name,
                  partner.service_type AS partner_service
           FROM claims c
           JOIN listings l ON l.id = c.listing_id
           JOIN users claimant ON claimant.id = c.claimant_id
           LEFT JOIN profiles cp ON cp.user_id = claimant.id
           JOIN users donor ON donor.id = l.donor_id
           LEFT JOIN profiles dp ON dp.user_id = donor.id
           LEFT JOIN delivery_requests d ON d.claim_id = c.id
           LEFT JOIN delivery_partners partner ON partner.id = d.partner_id
           WHERE c.id = ?""",
        (claim_id,),
    ).fetchone()
    if claim is None:
        abort(404)
    if g.user["id"] not in {claim["donor_id"], claim["claimant_id"]} and g.user["role"] != "admin":
        abort(403)
    if g.user["role"] == "admin":
        viewer = "admin"
    elif g.user["id"] == claim["donor_id"]:
        viewer = "donor"
    else:
        viewer = "claimant"

    timeline = [{"label": "Request submitted", "at": claim["created_at"], "tone": "cyan"}]
    if claim["status"] == "accepted":
        timeline.append({"label": "Request accepted", "at": claim["updated_at"], "tone": "success"})
    elif claim["status"] == "rejected":
        timeline.append({"label": "Request declined", "at": claim["updated_at"], "tone": "danger"})
    elif claim["status"] == "cancelled":
        timeline.append({"label": "Request withdrawn", "at": claim["updated_at"], "tone": "neutral"})
    if claim["handover_confirmed"]:
        timeline.append({"label": "Handover plan confirmed by Donor", "at": claim["updated_at"], "tone": "success"})
    if claim["status"] == "completed":
        timeline.append({"label": "Handover completed", "at": claim["updated_at"], "tone": "success"})

    conversation_id = _conversation_id_for(
        claim["listing_id"], claim["donor_id"], claim["claimant_id"]
    )
    delivery_step_index = -1
    if claim["delivery_status"] in DELIVERY_STEPS:
        delivery_step_index = DELIVERY_STEPS.index(claim["delivery_status"])
    return render_template(
        "dashboard/claim_detail.html",
        active_page="claims",
        claim=claim,
        viewer=viewer,
        timeline=timeline,
        conversation_id=conversation_id,
        delivery_step_index=delivery_step_index,
        delivery_steps=DELIVERY_STEPS,
        next_delivery_status=_next_delivery_status(claim["delivery_status"]),
    )


def _next_delivery_status(status: str | None) -> str | None:
    if status not in DELIVERY_STEPS:
        return None
    try:
        index = DELIVERY_STEPS.index(status)
    except ValueError:
        return None
    if index + 1 >= len(DELIVERY_STEPS):
        return None
    return DELIVERY_STEPS[index + 1]


@bp.route("/claims/<int:claim_id>/accept", methods=["POST"])
@login_required
def accept_claim(claim_id: int):
    db = get_db()
    claim = db.execute(
        """SELECT c.*, l.title, l.donor_id, l.id AS listing_id, u.name AS claimant_name,
                  (SELECT COUNT(*) FROM delivery_requests d WHERE d.claim_id = c.id) AS has_delivery
           FROM claims c JOIN listings l ON l.id = c.listing_id
           JOIN users u ON u.id = c.claimant_id WHERE c.id = ?""",
        (claim_id,),
    ).fetchone()
    if claim is None or claim["donor_id"] != g.user["id"]:
        abort(404)
    if claim["status"] != "pending":
        flash("This request has already been handled.", "info")
        return redirect(url_for("dashboard.incoming_claims"))
    note = (request.form.get("donor_note") or "").strip()[:800]
    now = stamp()
    db.execute(
        "UPDATE claims SET status = 'accepted', donor_note = ?, updated_at = ? WHERE id = ?",
        (note or "Request accepted. Let's arrange the handover through Messages.", now, claim_id),
    )
    db.execute("UPDATE listings SET status = 'reserved', updated_at = ? WHERE id = ?", (now, claim["listing_id"]))
    others = db.execute(
        "SELECT * FROM claims WHERE listing_id = ? AND id != ? AND status = 'pending'",
        (claim["listing_id"], claim_id),
    ).fetchall()
    for other in others:
        db.execute(
            "UPDATE claims SET status = 'rejected', donor_note = ?, updated_at = ? WHERE id = ?",
            ("Another request was accepted for this item.", now, other["id"]),
        )
        notify(
            other["claimant_id"],
            "claim_rejected",
            "Claim update",
            f"“{claim['title']}” has found a home with another community member. Your request was closed.",
            url_for("dashboard.my_claims"),
        )
    if claim["has_delivery"]:
        db.execute(
            """UPDATE delivery_requests SET status = 'awaiting_dispatch', updated_at = ?
               WHERE claim_id = ? AND status = 'request_accepted'""",
            (now, claim_id),
        )
        notify(
            claim["claimant_id"],
            "delivery_update",
            "Request accepted — delivery is being prepared",
            f"{g.user['name']} accepted your claim for “{claim['title']}”. The Partnered Delivery is now awaiting dispatch.",
            url_for("dashboard.claim_detail", claim_id=claim_id),
        )
    else:
        notify(
            claim["claimant_id"],
            "claim_accepted",
            "Your request was accepted",
            f"{g.user['name']} accepted your request for “{claim['title']}”. Arrange the Self Pickup through Messages.",
            url_for("dashboard.claim_detail", claim_id=claim_id),
        )
    notify(
        g.user["id"],
        "claim_accepted",
        "Handover in progress",
        f"You accepted {claim['claimant_name']}'s request for “{claim['title']}”.",
        url_for("dashboard.claim_detail", claim_id=claim_id),
    )
    db.commit()
    flash("Request accepted. The item is reserved and the Recipient has been notified.", "success")
    return redirect(url_for("dashboard.incoming_claims"))


@bp.route("/claims/<int:claim_id>/reject", methods=["POST"])
@login_required
def reject_claim(claim_id: int):
    db = get_db()
    claim = db.execute(
        """SELECT c.*, l.title, l.donor_id, u.name AS claimant_name
           FROM claims c JOIN listings l ON l.id = c.listing_id
           JOIN users u ON u.id = c.claimant_id WHERE c.id = ?""",
        (claim_id,),
    ).fetchone()
    if claim is None or claim["donor_id"] != g.user["id"]:
        abort(404)
    if claim["status"] != "pending":
        flash("This request has already been handled.", "info")
        return redirect(url_for("dashboard.incoming_claims"))
    note = (request.form.get("donor_note") or "").strip()[:800]
    now = stamp()
    db.execute(
        "UPDATE claims SET status = 'rejected', donor_note = ?, updated_at = ? WHERE id = ?",
        (note or "The Donor chose another request this time.", now, claim_id),
    )
    db.execute(
        "UPDATE delivery_requests SET status = 'cancelled', updated_at = ? WHERE claim_id = ?",
        (now, claim_id),
    )
    notify(
        claim["claimant_id"],
        "claim_rejected",
        "Claim update",
        f"Your request for “{claim['title']}” was not selected this time. There are more useful finds waiting.",
        url_for("dashboard.my_claims"),
    )
    db.commit()
    flash("The request was declined and the Recipient has been notified.", "info")
    return redirect(url_for("dashboard.incoming_claims"))


@bp.route("/claims/<int:claim_id>/confirm-handover", methods=["POST"])
@login_required
def confirm_handover(claim_id: int):
    db = get_db()
    claim = db.execute(
        """SELECT c.*, l.title, l.donor_id FROM claims c
           JOIN listings l ON l.id = c.listing_id WHERE c.id = ?""",
        (claim_id,),
    ).fetchone()
    if claim is None or claim["donor_id"] != g.user["id"]:
        abort(404)
    if claim["status"] != "accepted":
        flash("Only an accepted request can have its handover plan confirmed.", "error")
        return redirect(url_for("dashboard.claim_detail", claim_id=claim_id))
    now = stamp()
    db.execute(
        "UPDATE claims SET handover_confirmed = 1, updated_at = ? WHERE id = ?", (now, claim_id)
    )
    notify(
        claim["claimant_id"],
        "delivery_update",
        "Handover plan confirmed",
        f"{g.user['name']} confirmed the handover plan for “{claim['title']}”.",
        url_for("dashboard.claim_detail", claim_id=claim_id),
    )
    db.commit()
    flash("Handover plan confirmed. The Recipient can see the update.", "success")
    return redirect(url_for("dashboard.claim_detail", claim_id=claim_id))


@bp.route("/claims/<int:claim_id>/delivery/advance", methods=["POST"])
@login_required
def advance_delivery(claim_id: int):
    db = get_db()
    claim = db.execute(
        """SELECT c.*, l.title, l.id AS listing_id, l.donor_id,
                  d.id AS delivery_id, d.status AS delivery_status, d.fee AS delivery_fee,
                  d.partner_id, d.tracking_code
           FROM claims c JOIN listings l ON l.id = c.listing_id
           LEFT JOIN delivery_requests d ON d.claim_id = c.id
           WHERE c.id = ?""",
        (claim_id,),
    ).fetchone()
    if claim is None or g.user["id"] not in {claim["donor_id"], claim["claimant_id"]}:
        abort(404)
    if claim["status"] != "accepted" or not claim["delivery_id"]:
        flash("This delivery is not ready to advance.", "info")
        return redirect(url_for("dashboard.claim_detail", claim_id=claim_id))
    if claim["handover_confirmed"] != 1:
        flash("The Donor needs to confirm the handover plan before delivery can move forward.", "error")
        return redirect(url_for("dashboard.claim_detail", claim_id=claim_id))
    next_status = _next_delivery_status(claim["delivery_status"])
    if next_status is None:
        flash("This delivery has no further steps.", "info")
        return redirect(url_for("dashboard.claim_detail", claim_id=claim_id))
    now = stamp()
    db.execute(
        "UPDATE delivery_requests SET status = ?, updated_at = ? WHERE id = ?",
        (next_status, now, claim["delivery_id"]),
    )
    if next_status == "delivered":
        db.execute(
            "UPDATE claims SET status = 'completed', updated_at = ? WHERE id = ?",
            (now, claim_id),
        )
        db.execute(
            "UPDATE listings SET status = 'claimed', updated_at = ? WHERE id = ?",
            (now, claim["listing_id"]),
        )
        db.execute(
            """INSERT INTO transactions
               (user_id, type, reference_type, reference_id, amount, platform_fee, provider_payout,
                payment_method, description, status, created_at)
               VALUES (?, 'delivery', 'delivery_request', ?, ?, 0, ?, 'Partnered Delivery', ?, 'completed', ?)""",
            (
                claim["claimant_id"], claim["delivery_id"], claim["delivery_fee"],
                claim["delivery_fee"],
                f"Partnered Delivery fee — {claim['title']} ({claim['tracking_code']})",
                now,
            ),
        )
        notify(
            claim["donor_id"],
            "claim_accepted",
            "Your gift has been delivered",
            f"“{claim['title']}” completed its Partnered Delivery. Thank you for giving it a second purpose.",
            url_for("dashboard.donations"),
        )
    notify(
        claim["claimant_id"],
        "delivery_update",
        f"Delivery update: {DELIVERY_STATUS_LABELS[next_status]}",
        f"“{claim['title']}” is now {DELIVERY_STATUS_LABELS[next_status].lower()}.",
        url_for("dashboard.claim_detail", claim_id=claim_id),
    )
    notify(
        claim["donor_id"],
        "delivery_update",
        f"Delivery update: {DELIVERY_STATUS_LABELS[next_status]}",
        f"The Partnered Delivery for “{claim['title']}” is now {DELIVERY_STATUS_LABELS[next_status].lower()}.",
        url_for("dashboard.claim_detail", claim_id=claim_id),
    )
    db.commit()
    flash(f"Delivery updated: {DELIVERY_STATUS_LABELS[next_status]}.", "success")
    return redirect(url_for("dashboard.claim_detail", claim_id=claim_id))


@bp.route("/claims/mine")
@login_required
def my_claims():
    db = get_db()
    status_filter = request.args.get("status") or "all"
    sql = """SELECT c.*, l.title AS listing_title, l.id AS listing_id, l.status AS listing_status,
                    l.city AS listing_city, l.area AS listing_area, l.donor_id,
                    l.condition AS listing_condition, l.item_size,
                    u.name AS donor_name, p.avatar_url AS donor_avatar,
                    CASE WHEN c.status IN ('accepted', 'completed') THEN p.contact_number END AS donor_contact,
                    (SELECT image_url FROM listing_images li WHERE li.listing_id = l.id
                     ORDER BY li.sort_order, li.id LIMIT 1) AS listing_image,
                    d.id AS delivery_id, d.status AS delivery_status, d.fee AS delivery_fee,
                    d.tracking_code, dp.name AS partner_name
             FROM claims c JOIN listings l ON l.id = c.listing_id
             JOIN users u ON u.id = l.donor_id
             LEFT JOIN profiles p ON p.user_id = u.id
             LEFT JOIN delivery_requests d ON d.claim_id = c.id
             LEFT JOIN delivery_partners dp ON dp.id = d.partner_id
             WHERE c.claimant_id = ?"""
    params: list = [g.user["id"]]
    if status_filter != "all":
        sql += " AND c.status = ?"
        params.append(status_filter)
    sql += " ORDER BY c.created_at DESC"
    claims = [dict(row) for row in db.execute(sql, params).fetchall()]
    for claim in claims:
        claim["conversation_id"] = _conversation_id_for(claim["listing_id"], claim["donor_id"], claim["claimant_id"])
    counts = {
        row["status"]: row["total"]
        for row in db.execute(
            "SELECT status, COUNT(*) AS total FROM claims WHERE claimant_id = ? GROUP BY status",
            (g.user["id"],),
        ).fetchall()
    }
    counts["all"] = sum(counts.values())
    return render_template(
        "dashboard/claims_mine.html",
        active_page="requests",
        claims=claims,
        counts=counts,
        status_filter=status_filter,
    )


def _complete_claim(claim: dict, actor_id: int) -> None:
    db = get_db()
    now = stamp()
    db.execute("UPDATE claims SET status = 'completed', updated_at = ? WHERE id = ?", (now, claim["id"]))
    db.execute(
        "UPDATE listings SET status = 'claimed', updated_at = ? WHERE id = ?",
        (now, claim["listing_id"]),
    )
    notify(
        claim["donor_id"],
        "claim_accepted",
        "Donation completed",
        f"The handover for “{claim['title']}” is complete. Thank you for giving it a second purpose.",
        url_for("dashboard.donations"),
    )
    notify(
        claim["claimant_id"],
        "claim_accepted",
        "Item received",
        f"“{claim['title']}” is now yours. Every reused item keeps valuable resources in circulation.",
        url_for("dashboard.my_claims"),
    )
    db.commit()


@bp.route("/claims/<int:claim_id>/complete", methods=["POST"])
@login_required
def complete_claim(claim_id: int):
    db = get_db()
    claim = db.execute(
        """SELECT c.*, l.title, l.id AS listing_id, l.donor_id,
                  (SELECT status FROM delivery_requests d WHERE d.claim_id = c.id) AS delivery_status
           FROM claims c JOIN listings l ON l.id = c.listing_id WHERE c.id = ?""",
        (claim_id,),
    ).fetchone()
    if claim is None or claim["claimant_id"] != g.user["id"]:
        abort(404)
    if claim["status"] != "accepted":
        flash("Only an accepted request can be completed.", "error")
        return redirect(url_for("dashboard.my_claims"))
    if claim["receive_method"] == "delivery" and claim["delivery_status"] != "delivered":
        flash("The Partnered Delivery must reach Successfully Delivered before the request can be completed.", "error")
        return redirect(url_for("dashboard.claim_detail", claim_id=claim_id))
    _complete_claim(claim, g.user["id"])
    flash("Handover confirmed. Thank you for keeping useful things in circulation.", "success")
    return redirect(url_for("dashboard.my_claims"))


@bp.route("/claims/<int:claim_id>/donor-complete", methods=["POST"])
@login_required
def complete_claim_as_donor(claim_id: int):
    db = get_db()
    claim = db.execute(
        """SELECT c.*, l.title, l.id AS listing_id, l.donor_id,
                  (SELECT status FROM delivery_requests d WHERE d.claim_id = c.id) AS delivery_status
           FROM claims c JOIN listings l ON l.id = c.listing_id WHERE c.id = ?""",
        (claim_id,),
    ).fetchone()
    if claim is None or claim["donor_id"] != g.user["id"]:
        abort(404)
    if claim["status"] != "accepted":
        flash("Only an accepted request can be completed.", "error")
        return redirect(url_for("dashboard.claim_detail", claim_id=claim_id))
    if claim["receive_method"] == "delivery" and claim["delivery_status"] != "delivered":
        flash("The Partnered Delivery has not been marked Successfully Delivered yet.", "error")
        return redirect(url_for("dashboard.claim_detail", claim_id=claim_id))
    _complete_claim(claim, g.user["id"])
    flash("Handover marked complete. Both sides can see the finished record.", "success")
    return redirect(url_for("dashboard.claim_detail", claim_id=claim_id))


@bp.route("/claims/<int:claim_id>/cancel", methods=["POST"])
@login_required
def cancel_claim(claim_id: int):
    db = get_db()
    claim = db.execute(
        """SELECT c.*, l.title, l.id AS listing_id, l.donor_id,
                  (SELECT status FROM delivery_requests d WHERE d.claim_id = c.id) AS delivery_status
           FROM claims c JOIN listings l ON l.id = c.listing_id WHERE c.id = ?""",
        (claim_id,),
    ).fetchone()
    if claim is None or claim["claimant_id"] != g.user["id"]:
        abort(404)
    if claim["status"] not in {"pending", "accepted"}:
        flash("This request can no longer be withdrawn.", "info")
        return redirect(url_for("dashboard.my_claims"))
    if claim["delivery_status"] in {"in_progress", "arriving_soon", "delivered"}:
        flash("This delivery is already moving. Please contact the Donor or support.", "error")
        return redirect(url_for("dashboard.my_claims"))
    now = stamp()
    db.execute(
        "UPDATE claims SET status = 'cancelled', updated_at = ? WHERE id = ?", (now, claim_id)
    )
    db.execute(
        "UPDATE delivery_requests SET status = 'cancelled', updated_at = ? WHERE claim_id = ?",
        (now, claim_id),
    )
    if claim["status"] == "accepted":
        db.execute(
            "UPDATE listings SET status = 'available', updated_at = ? WHERE id = ?",
            (now, claim["listing_id"]),
        )
    notify(
        claim["donor_id"],
        "claim_rejected",
        "A claim was withdrawn",
        f"The Recipient withdrew their request for “{claim['title']}”. Your listing is available again.",
        url_for("dashboard.donations"),
    )
    db.commit()
    flash("Your claim has been withdrawn.", "info")
    return redirect(url_for("dashboard.my_claims"))


@bp.route("/claimed")
@login_required
def claimed():
    return redirect(url_for("dashboard.my_claims", status="completed"))


@bp.route("/saved")
@login_required
def saved():
    db = get_db()
    saved_ids = [row["listing_id"] for row in db.execute(
        "SELECT listing_id FROM saved_listings WHERE user_id = ? ORDER BY created_at DESC",
        (g.user["id"],),
    ).fetchall()]
    if saved_ids:
        placeholders = ",".join("?" for _ in saved_ids)
        rows = db.execute(
            LISTING_CARD_SQL
            + f" WHERE l.id IN ({placeholders}) AND l.status != 'removed' ORDER BY l.created_at DESC",
            saved_ids,
        ).fetchall()
        listings = attach_listing_state([dict(row) for row in rows])
    else:
        listings = []
    return render_template(
        "dashboard/saved.html", active_page="saved", listings=listings
    )


@bp.route("/notifications")
@login_required
def notifications():
    db = get_db()
    items = db.execute(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY is_read, created_at DESC",
        (g.user["id"],),
    ).fetchall()
    return render_template(
        "dashboard/notifications.html", active_page="notifications", notifications=items
    )


@bp.route("/notifications/<int:notification_id>/open")
@login_required
def open_notification(notification_id: int):
    db = get_db()
    item = db.execute(
        "SELECT * FROM notifications WHERE id = ? AND user_id = ?",
        (notification_id, g.user["id"]),
    ).fetchone()
    if item is None:
        abort(404)
    db.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notification_id,))
    db.commit()
    return redirect(safe_next(item["link"], url_for("dashboard.notifications")))


@bp.route("/notifications/read-all", methods=["POST"])
@login_required
def read_all_notifications():
    db = get_db()
    db.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (g.user["id"],))
    db.commit()
    flash("All caught up. Your notifications are marked as read.", "success")
    return redirect(url_for("dashboard.notifications"))


@bp.route("/messages")
@login_required
def messages():
    db = get_db()
    q = (request.args.get("q") or "").strip()[:120]
    conversations = conversation_list(g.user["id"])
    if q:
        needle = q.lower()
        conversations = [
            item for item in conversations
            if needle in (item["other_name"] or "").lower()
            or needle in (item["listing_title"] or "").lower()
            or needle in (item["preview"] or "").lower()
        ]
    selected_id = request.args.get("conversation", type=int)
    selected = find_conversation(selected_id, g.user["id"]) if selected_id else None
    messages_list: list[dict] = []
    if selected:
        mark_conversation_read(selected["id"], g.user["id"])
        messages_list = conversation_messages(selected["id"])
        db.commit()
    return render_template(
        "dashboard/messages.html",
        active_page="messages",
        conversations=conversations,
        selected=selected,
        messages=messages_list,
        q=q,
    )


@bp.route("/messages/<int:conversation_id>")
@login_required
def conversation(conversation_id: int):
    return redirect(url_for("dashboard.messages", conversation=conversation_id))


@bp.route("/messages/start")
@login_required
def start_conversation():
    listing_id = request.args.get("listing_id", type=int)
    other_id = request.args.get("user_id", type=int)
    claim_id = request.args.get("claim_id", type=int)
    if not listing_id:
        abort(404)
    listing = get_listing_detail(listing_id)
    if listing is None:
        abort(404)
    db = get_db()
    if g.user["id"] == listing["donor_id"]:
        if not other_id or other_id == g.user["id"]:
            flash("Choose an interested Recipient to start a conversation.", "info")
            return redirect(url_for("dashboard.incoming_claims"))
        recipient = db.execute(
            """SELECT u.id FROM users u JOIN claims c ON c.claimant_id = u.id
               WHERE u.id = ? AND c.listing_id = ? LIMIT 1""",
            (other_id, listing_id),
        ).fetchone()
        if recipient is None:
            flash("That person has not sent a request for this listing.", "error")
            return redirect(url_for("dashboard.donations"))
        donor_id, recipient_id = g.user["id"], other_id
    else:
        donor_id, recipient_id = listing["donor_id"], g.user["id"]
    conversation_id = get_or_create_conversation(
        donor_id, recipient_id, listing_id, claim_id=claim_id
    )
    db.commit()
    return redirect(url_for("dashboard.messages", conversation=conversation_id))


@bp.route("/messages/<int:conversation_id>/send", methods=["POST"])
@login_required
def send_message(conversation_id: int):
    conversation = find_conversation(conversation_id, g.user["id"])
    if conversation is None:
        abort(404)
    body = (request.form.get("body") or "").strip()
    attachment_url = None
    files = request.files.getlist("attachment")
    if files and any(f and f.filename for f in files):
        saved, error = save_image_uploads(files[:1])
        if error:
            flash(error, "error")
            return redirect(url_for("dashboard.messages", conversation=conversation_id))
        attachment_url = saved[0] if saved else None
    if request.form.get("use_listing_photo") == "on" and conversation.get("listing_image"):
        attachment_url = conversation["listing_image"]
    if not body and not attachment_url:
        flash("Write a message or attach a photo before sending.", "error")
        return redirect(url_for("dashboard.messages", conversation=conversation_id))
    if len(body) > 2000:
        flash("Please keep messages under 2,000 characters.", "error")
        return redirect(url_for("dashboard.messages", conversation=conversation_id))
    db = get_db()
    now = stamp()
    db.execute(
        """INSERT INTO messages (conversation_id, sender_id, body, attachment_url, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (conversation_id, g.user["id"], body or "Shared a photo", attachment_url, now),
    )
    db.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))
    recipient_id = conversation["recipient_id"] if conversation["is_donor"] else conversation["donor_id"]
    notify(
        recipient_id,
        "message",
        f"New message from {g.user['name']}" if g.user["id"] == conversation["donor_id"] else f"New message from {g.user['name']}",
        body[:140] if body else "Shared a photo in your conversation.",
        url_for("dashboard.messages", conversation=conversation_id),
    )
    db.commit()
    return redirect(url_for("dashboard.messages", conversation=conversation_id))


@bp.route("/deliveries")
@login_required
def deliveries():
    return redirect(url_for("dashboard.my_claims"))


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action") or "profile"
        if action == "password":
            current_password = request.form.get("current_password") or ""
            new_password = request.form.get("new_password") or ""
            confirm = request.form.get("confirm_password") or ""
            row = db.execute("SELECT password_hash FROM users WHERE id = ?", (g.user["id"],)).fetchone()
            errors = []
            if not row or not check_password_hash(row["password_hash"], current_password):
                errors.append("Your current password is not correct.")
            if len(new_password) < 8 or not any(c.isalpha() for c in new_password) or not any(c.isdigit() for c in new_password):
                errors.append("The new password needs at least 8 characters, including a letter and a number.")
            if new_password != confirm:
                errors.append("The new passwords do not match.")
            if errors:
                for error in errors:
                    flash(error, "error")
            else:
                db.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (generate_password_hash(new_password), g.user["id"]),
                )
                db.commit()
                flash("Your password has been updated.", "success")
            return redirect(url_for("dashboard.settings"))

        name = (request.form.get("name") or "").strip()
        city = (request.form.get("city") or "").strip()
        location = (request.form.get("location") or "").strip()
        contact = (request.form.get("contact_number") or "").strip()
        bio = (request.form.get("bio") or "").strip()
        errors = []
        if len(name) < 2 or len(name) > 80:
            errors.append("Please add your full name.")
        if city not in CITIES:
            errors.append("Choose your city.")
        if len(location) > 120:
            errors.append("Keep your area description under 120 characters.")
        if contact and not all(character.isdigit() or character in " +-()" for character in contact):
            errors.append("Use a valid phone number format.")
        if len(bio) > 500:
            errors.append("Keep your bio under 500 characters.")
        avatar_url = None
        if request.files.get("avatar") and request.files["avatar"].filename:
            avatar_url, avatar_error = save_avatar(request.files["avatar"])
            if avatar_error:
                errors.append(avatar_error)
        if errors:
            for error in errors:
                flash(error, "error")
            return redirect(url_for("dashboard.settings"))
        latitude, longitude = LOCATION_COORDS[city] if city in LOCATION_COORDS else (None, None)
        db.execute("UPDATE users SET name = ? WHERE id = ?", (name, g.user["id"]))
        db.execute(
            """UPDATE profiles SET location = ?, city = ?, latitude = ?, longitude = ?, contact_number = ?,
                      bio = ? {avatar_sql}
               WHERE user_id = ?""".format(avatar_sql=", avatar_url = ?" if avatar_url else ""),
            (
                location or city, city, latitude, longitude, contact or None, bio or None,
                *((avatar_url,) if avatar_url else ()),
                g.user["id"],
            ),
        )
        db.commit()
        flash("Your profile has been updated.", "success")
        return redirect(url_for("dashboard.settings"))
    profile = db.execute(
        """SELECT u.id, u.name, u.email, u.role, u.status, u.created_at, u.email_verified,
                  p.* FROM users u LEFT JOIN profiles p ON p.user_id = u.id WHERE u.id = ?""",
        (g.user["id"],),
    ).fetchone()
    stats = {
        "donated": db.execute(
            """SELECT COUNT(*) FROM claims c JOIN listings l ON l.id = c.listing_id
               WHERE l.donor_id = ? AND c.status = 'completed'""",
            (g.user["id"],),
        ).fetchone()[0],
        "claimed": db.execute(
            "SELECT COUNT(*) FROM claims WHERE claimant_id = ? AND status = 'completed'",
            (g.user["id"],),
        ).fetchone()[0],
    }
    return render_template(
        "dashboard/settings.html",
        active_page="settings",
        profile=profile,
        stats=stats,
    )
