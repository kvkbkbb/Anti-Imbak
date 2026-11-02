"""Shared infrastructure for Anti-Imbak.

Contains the database connection lifecycle, authentication/CSRF helpers,
notification and upload utilities, listing queries and presentation filters.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit

from flask import abort, current_app, flash, g, redirect, request, session, url_for
from werkzeug.utils import secure_filename

from db import DATABASE_PATH, LOCATION_COORDS, haversine_km

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

CITIES = list(LOCATION_COORDS.keys())
CONDITIONS = ["Like New", "Good", "Fair", "For Repair", "Nonfunctional"]
CONDITION_TONE = {
    "Like New": "cyan",
    "Good": "violet",
    "Fair": "amber",
    "For Repair": "warm",
    "Nonfunctional": "danger",
}
CONDITION_LABELS = {
    "Like New": "Like New",
    "Good": "Good",
    "Fair": "Fair",
    "For Repair": "For Repair",
    "Nonfunctional": "Nonfunctional",
}
ITEM_SIZES = ["small", "medium", "large"]
ITEM_SIZE_LABELS = {"small": "Small", "medium": "Medium", "large": "Large / bulky"}
LISTING_STATUSES = ["available", "reserved", "claimed", "unavailable"]
LISTING_STATUS_LABELS = {
    "available": "Available",
    "reserved": "Reserved",
    "claimed": "Claimed",
    "unavailable": "Unavailable",
    "removed": "Removed",
}
CLAIM_STATUS_LABELS = {
    "pending": "Awaiting review",
    "accepted": "Accepted",
    "rejected": "Not selected",
    "completed": "Completed",
    "cancelled": "Withdrawn",
}
DELIVERY_STATUS_LABELS = {
    "request_accepted": "Request Accepted",
    "awaiting_dispatch": "Awaiting Dispatch",
    "in_progress": "Delivery in Progress",
    "arriving_soon": "Arriving Soon",
    "delivered": "Successfully Delivered",
    "cancelled": "Cancelled",
}
DELIVERY_STEPS = ["request_accepted", "awaiting_dispatch", "in_progress", "arriving_soon", "delivered"]
DELIVERY_STEP_COPY = {
    "request_accepted": "The delivery request is attached to the claim.",
    "awaiting_dispatch": "The Donor is preparing the item for the partner.",
    "in_progress": "The partner is moving the item to the Recipient.",
    "arriving_soon": "The Recipient should be ready to receive the item.",
    "delivered": "The Recipient confirmed the handover.",
}
REPORT_REASONS = [
    "Suspicious listing",
    "Misleading description",
    "Inappropriate images",
    "Fraudulent account",
    "Harassment",
    "Unsafe transaction",
    "Other safety concern",
]
DISPUTE_CATEGORIES = [
    "Item not as described",
    "Item not received",
    "Handover arrangement problems",
    "Delivery problems",
    "Miscommunication between users",
    "Inappropriate user behavior",
    "Other concerns",
]
DISPUTE_STATUSES = ["open", "under_review", "resolved", "closed"]
DISPUTE_STATUS_LABELS = {
    "open": "Open",
    "under_review": "Under review",
    "resolved": "Resolved",
    "closed": "Closed",
}
DISPUTE_PRIORITIES = ["low", "medium", "high", "urgent"]
PRIORITY_LABELS = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "urgent": "Urgent",
}
SUPPORT_CATEGORIES = [
    "Account problems",
    "Technical issues",
    "Donation listing problems",
    "Claim request concerns",
    "Delivery concerns",
    "Payment concerns",
    "Suggestions",
    "General inquiries",
]
SUPPORT_STATUSES = ["open", "in_progress", "resolved", "closed"]
SUPPORT_STATUS_LABELS = {
    "open": "Open",
    "in_progress": "In progress",
    "resolved": "Resolved",
    "closed": "Closed",
}
DEMO_ROLES = {
    "public": {"label": "Public Marketplace", "short": "Public", "icon": "globe"},
    "donor": {"label": "Donor", "short": "Donor", "icon": "gift"},
    "recipient": {"label": "Recipient", "short": "Recipient", "icon": "hand-heart"},
    "admin": {"label": "Administrator", "short": "Admin", "icon": "shield-check"},
}
DEMO_ACCOUNTS = {
    "donor": "maya@antiimbak.com",
    "recipient": "josh@antiimbak.com",
    "admin": "admin@antiimbak.com",
}
FEATURED_PACKAGES = {
    "standard": {
        "name": "Standard",
        "tagline": "Free, as it should be",
        "fee": 0.0,
        "days": 0,
        "eyebrow": "Included",
        "features": [
            "Visible in search and category browsing",
            "Free claim requests and Partnered Delivery",
            "Safety reminders and community reporting",
        ],
    },
    "featured": {
        "name": "Featured",
        "tagline": "A gentle lift for a good find",
        "fee": 149.0,
        "days": 14,
        "eyebrow": "Most popular",
        "features": [
            "Top placement in relevant categories",
            "A visible Featured label for 14 days",
            "Included in the homepage discovery rail",
            "Optional alerts to nearby opted-in members",
        ],
    },
    "premium": {
        "name": "Premium Boost",
        "tagline": "Maximum visibility for 30 days",
        "fee": 399.0,
        "days": 30,
        "eyebrow": "Best reach",
        "features": [
            "Priority placement above other free listings",
            "A visible Featured label for 30 days",
            "Homepage spotlight eligibility",
            "Optional alerts to nearby opted-in members",
        ],
    },
}
FEATURED_PACKAGES = {k: v for k, v in FEATURED_PACKAGES.items()}
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_IMAGES_PER_LISTING = 5

# ---------------------------------------------------------------------------
# Database lifecycle
# ---------------------------------------------------------------------------


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        connection = sqlite3.connect(DATABASE_PATH)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        g.db = connection
    return g.db


def close_db(_error=None) -> None:
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


# ---------------------------------------------------------------------------
# Time and formatting
# ---------------------------------------------------------------------------


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def stamp(value: datetime | None = None) -> str:
    return (value or utcnow()).strftime("%Y-%m-%d %H:%M:%S")


def parse_stamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def time_ago(value: str | None) -> str:
    parsed = parse_stamp(value)
    if not parsed:
        return ""
    seconds = (utcnow() - parsed).total_seconds()
    future = seconds < 0
    seconds = abs(seconds)
    if seconds < 60:
        return "Just now"
    minutes = int(seconds // 60)
    if minutes < 60:
        phrase = f"{minutes} min"
    elif minutes < 1440:
        hours = minutes // 60
        phrase = f"{hours} hr"
    elif minutes < 10080:
        days = minutes // 1440
        phrase = f"{days} day"
    elif minutes < 43200:
        weeks = minutes // 10080
        phrase = f"{weeks} wk"
    else:
        return parsed.strftime("%b %d, %Y")
    return f"in {phrase}" if future else f"{phrase} ago"


def long_date(value: str | None, include_year: bool = True) -> str:
    parsed = parse_stamp(value)
    if not parsed:
        return "—"
    return parsed.strftime("%b %d, %Y" if include_year else "%b %d")


def date_iso(value: str | None) -> str:
    parsed = parse_stamp(value)
    return parsed.strftime("%Y-%m-%d") if parsed else ""


def money(value) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        return "₱0.00"
    return f"₱{amount:,.2f}"


def compact_money(value) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        return "₱0"
    if amount >= 1_000_000:
        return f"₱{amount / 1_000_000:.1f}M"
    if amount >= 10_000:
        return f"₱{amount / 1_000:.1f}k"
    if amount.is_integer():
        return f"₱{int(amount):,}"
    return f"₱{amount:,.2f}"


def initials(name: str | None) -> str:
    parts = [part for part in str(name or "").split() if part]
    if not parts:
        return "AI"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def plural(value: int, singular: str, plural_word: str | None = None) -> str:
    return singular if value == 1 else (plural_word or singular + "s")


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]*>", "", value or "")


# ---------------------------------------------------------------------------
# Authentication and security
# ---------------------------------------------------------------------------


def load_logged_in_user() -> None:
    g.user = None
    user_id = session.get("user_id")
    if not user_id:
        return
    row = get_db().execute(
        """SELECT u.id, u.name, u.email, u.role, u.status, u.created_at, u.last_login,
                  p.avatar_url, p.contact_number, p.location, p.city, p.latitude,
                  p.longitude, p.bio, p.verified, p.member_since
           FROM users u LEFT JOIN profiles p ON p.user_id = u.id
           WHERE u.id = ?""",
        (user_id,),
    ).fetchone()
    if row is None:
        session.clear()
        return
    if row["status"] == "suspended":
        session.clear()
        flash("This account is currently suspended. Contact hello@antiimbak.ph for help.", "error")
        return
    g.user = dict(row)


def ensure_csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def validate_csrf() -> None:
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        expected = session.get("_csrf_token")
        provided = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not expected or not provided or not secrets.compare_digest(expected, provided):
            abort(400, description="Your form session expired. Please refresh the page and try again.")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            flash("Log in to continue — your next step is waiting.", "info")
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            flash("Log in with an administrator account to continue.", "info")
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        if g.user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def current_perspective() -> str:
    """Return the active demonstration perspective for this request."""
    if not g.get("user"):
        return "public"
    explicit = session.get("demo_role")
    if explicit in {"donor", "recipient", "admin"}:
        return explicit
    user = g.user
    if user["role"] == "admin":
        return "admin"
    email = (user.get("email") or "").lower()
    if email == DEMO_ACCOUNTS["donor"]:
        return "donor"
    if email == DEMO_ACCOUNTS["recipient"]:
        return "recipient"
    db = get_db()
    owns = db.execute(
        "SELECT 1 FROM listings WHERE donor_id = ? AND status != 'removed' LIMIT 1",
        (user["id"],),
    ).fetchone()
    return "donor" if owns else "recipient"


def safe_next(target: str | None, fallback: str | None = None) -> str:
    fallback = fallback or url_for("public.index")
    if not target:
        return fallback
    target = target.strip()
    if target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return fallback


def is_safe_redirect_url(target: str | None) -> bool:
    if not target:
        return False
    if target.startswith("/") and not target.startswith("//"):
        return True
    parsed = urlsplit(target)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


# ---------------------------------------------------------------------------
# Content and listing helpers
# ---------------------------------------------------------------------------


def get_categories(include_inactive: bool = False) -> list[dict]:
    sql = """SELECT c.*,
                    (SELECT COUNT(*) FROM listings l
                     WHERE l.category_id = c.id AND l.status != 'removed') AS listing_count
             FROM categories c"""
    if not include_inactive:
        sql += " WHERE c.active = 1"
    sql += " ORDER BY c.sort_order, c.name"
    return [dict(row) for row in get_db().execute(sql).fetchall()]


def get_active_ad(placement: str, category_id: int | None = None, track: bool = True) -> dict | None:
    now = stamp()
    sql = """SELECT a.*, c.slug AS category_slug
             FROM advertisements a
             LEFT JOIN categories c ON c.id = a.category_id
             WHERE a.status = 'active' AND a.starts_at <= ? AND a.ends_at >= ?
               AND a.placement = ?"""
    params: list = [now, now, placement]
    if category_id and placement == "category":
        sql += " AND a.category_id = ?"
        params.append(category_id)
    sql += " ORDER BY a.starts_at DESC LIMIT 1"
    row = get_db().execute(sql, params).fetchone()
    if row is None:
        return None
    ad = dict(row)
    if track:
        get_db().execute("UPDATE advertisements SET impressions = impressions + 1 WHERE id = ?", (ad["id"],))
    return ad


def record_ad_click(ad_id: int) -> None:
    get_db().execute("UPDATE advertisements SET clicks = clicks + 1 WHERE id = ?", (ad_id,))


def get_my_saved_ids() -> set[int]:
    if not g.get("user"):
        return set()
    rows = get_db().execute(
        "SELECT listing_id FROM saved_listings WHERE user_id = ?", (g.user["id"],)
    ).fetchall()
    return {row["listing_id"] for row in rows}


LISTING_CARD_SQL = """
    SELECT l.*, c.name AS category_name, c.slug AS category_slug, c.icon AS category_icon,
           u.name AS donor_name, u.created_at AS donor_joined,
           p.avatar_url AS donor_avatar, p.verified AS donor_verified,
           (SELECT image_url FROM listing_images li WHERE li.listing_id = l.id
            ORDER BY li.sort_order, li.id LIMIT 1) AS primary_image,
           (SELECT COUNT(*) FROM listing_images li WHERE li.listing_id = l.id) AS image_count,
           (SELECT COUNT(*) FROM claims cl WHERE cl.listing_id = l.id AND cl.status = 'pending') AS pending_claims,
           (SELECT COUNT(*) FROM saved_listings sl WHERE sl.listing_id = l.id) AS save_count,
           (julianday('now') - julianday(l.created_at)) AS age_days
    FROM listings l
    JOIN categories c ON c.id = l.category_id
    JOIN users u ON u.id = l.donor_id
    LEFT JOIN profiles p ON p.user_id = u.id
"""


def attach_listing_state(listings: list[dict], reference: tuple[float, float] | None = None) -> list[dict]:
    saved_ids = get_my_saved_ids()
    for listing in listings:
        listing["is_saved"] = listing["id"] in saved_ids
        if reference:
            listing["distance_km"] = haversine_km(
                reference, (listing["latitude"], listing["longitude"])
            )
    return listings


def reference_coordinates(location_filter: str | None = None) -> tuple[float, float]:
    if location_filter and location_filter in LOCATION_COORDS:
        return LOCATION_COORDS[location_filter]
    if g.get("user") and g.user.get("latitude") and g.user.get("longitude"):
        return (g.user["latitude"], g.user["longitude"])
    return LOCATION_COORDS["Quezon City"]


def listing_coordinates(city: str, seed_text: str) -> tuple[float, float]:
    base_lat, base_lon = LOCATION_COORDS.get(city, LOCATION_COORDS["Quezon City"])
    digest = hashlib.sha1(seed_text.encode("utf-8")).hexdigest()
    lat_offset = (int(digest[:4], 16) % 160 - 80) / 100000
    lon_offset = (int(digest[4:8], 16) % 160 - 80) / 100000
    return round(base_lat + lat_offset, 6), round(base_lon + lon_offset, 6)


def get_listing_detail(listing_id: int, allow_removed: bool = False) -> dict | None:
    row = get_db().execute(
        """SELECT l.*, c.name AS category_name, c.slug AS category_slug, c.icon AS category_icon,
                  u.name AS donor_name, u.email AS donor_email, u.created_at AS donor_joined,
                  p.avatar_url AS donor_avatar, p.bio AS donor_bio, p.verified AS donor_verified,
                  p.city AS donor_city,
                  (SELECT COUNT(*) FROM listings l2 WHERE l2.donor_id = u.id AND l2.status != 'removed') AS donor_listing_count,
                  (SELECT COUNT(*) FROM claims c2 JOIN listings l3 ON l3.id = c2.listing_id
                   WHERE l3.donor_id = u.id AND c2.status = 'completed') AS donor_gifts
           FROM listings l
           JOIN categories c ON c.id = l.category_id
           JOIN users u ON u.id = l.donor_id
           LEFT JOIN profiles p ON p.user_id = u.id
           WHERE l.id = ?""",
        (listing_id,),
    ).fetchone()
    if row is None:
        return None
    listing = dict(row)
    if listing["status"] == "removed" and not allow_removed:
        return None
    listing["images"] = [
        dict(img)
        for img in get_db().execute(
            "SELECT * FROM listing_images WHERE listing_id = ? ORDER BY sort_order, id", (listing_id,)
        ).fetchall()
    ]
    return listing


def may_admin() -> bool:
    return bool(g.get("user") and g.user["role"] == "admin")


# ---------------------------------------------------------------------------
# Notifications and logs
# ---------------------------------------------------------------------------


def notify(user_id: int, type_: str, title: str, message: str, link: str | None = None) -> None:
    get_db().execute(
        """INSERT INTO notifications (user_id, type, title, message, link, is_read)
           VALUES (?, ?, ?, ?, ?, 0)""",
        (user_id, type_, title, message, link),
    )


def notify_admins(title: str, message: str, link: str | None = None) -> None:
    admins = get_db().execute("SELECT id FROM users WHERE role = 'admin' AND status = 'active'").fetchall()
    for admin in admins:
        notify(admin["id"], "announcement", title, message, link)


def log_admin(action: str, target_type: str, target_id: int | None, details: str = "") -> None:
    if not g.get("user"):
        return
    get_db().execute(
        """INSERT INTO admin_logs (admin_id, action, target_type, target_id, details)
           VALUES (?, ?, ?, ?, ?)""",
        (g.user["id"], action, target_type, target_id, details),
    )


def unread_notification_count() -> int:
    if not g.get("user"):
        return 0
    row = get_db().execute(
        "SELECT COUNT(*) AS total FROM notifications WHERE user_id = ? AND is_read = 0",
        (g.user["id"],),
    ).fetchone()
    return int(row["total"] if row else 0)


def unread_message_count() -> int:
    if not g.get("user"):
        return 0
    row = get_db().execute(
        """SELECT COUNT(*) AS total FROM messages m
           JOIN conversations c ON c.id = m.conversation_id
           WHERE (c.donor_id = ? OR c.recipient_id = ?)
             AND m.sender_id != ? AND m.read_at IS NULL""",
        (g.user["id"], g.user["id"], g.user["id"]),
    ).fetchone()
    return int(row["total"] if row else 0)


def conversation_list(user_id: int | None = None) -> list[dict]:
    if not user_id:
        if not g.get("user"):
            return []
        user_id = g.user["id"]
    rows = get_db().execute(
        """SELECT c.*, l.title AS listing_title, l.status AS listing_status, l.city AS listing_city,
                  g.name AS donor_name, gp.avatar_url AS donor_avatar,
                  t.name AS recipient_name, tp.avatar_url AS recipient_avatar,
                  (SELECT image_url FROM listing_images li WHERE li.listing_id = l.id
                   ORDER BY li.sort_order, li.id LIMIT 1) AS listing_image,
                  (SELECT body FROM messages m WHERE m.conversation_id = c.id
                   ORDER BY m.created_at DESC, m.id DESC LIMIT 1) AS last_body,
                  (SELECT created_at FROM messages m WHERE m.conversation_id = c.id
                   ORDER BY m.created_at DESC, m.id DESC LIMIT 1) AS last_message_at,
                  (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id
                   AND m.sender_id != ? AND m.read_at IS NULL) AS unread_count
           FROM conversations c
           LEFT JOIN listings l ON l.id = c.listing_id
           LEFT JOIN profiles gp ON gp.user_id = c.donor_id
           LEFT JOIN profiles tp ON tp.user_id = c.recipient_id
           JOIN users g ON g.id = c.donor_id
           JOIN users t ON t.id = c.recipient_id
           WHERE c.donor_id = ? OR c.recipient_id = ?
           ORDER BY COALESCE(last_message_at, c.updated_at) DESC, c.id DESC""",
        (user_id, user_id, user_id),
    ).fetchall()
    conversations = []
    for row in rows:
        item = dict(row)
        item["is_donor"] = item["donor_id"] == user_id
        item["other_name"] = item["recipient_name"] if item["is_donor"] else item["donor_name"]
        item["other_avatar"] = item["recipient_avatar"] if item["is_donor"] else item["donor_avatar"]
        item["other_id"] = item["recipient_id"] if item["is_donor"] else item["donor_id"]
        item["other_role"] = "Recipient" if item["is_donor"] else "Donor"
        item["preview"] = (item.get("last_body") or "Start the conversation").replace("\n", " ")[:95]
        conversations.append(item)
    return conversations


def find_conversation(conversation_id: int, user_id: int) -> dict | None:
    row = get_db().execute(
        """SELECT c.*, l.title AS listing_title, l.status AS listing_status, l.city AS listing_city,
                  l.area AS listing_area, l.donor_id,
                  g.name AS donor_name, g.email AS donor_email,
                  t.name AS recipient_name, t.email AS recipient_email,
                  gp.avatar_url AS donor_avatar, tp.avatar_url AS recipient_avatar,
                  (SELECT image_url FROM listing_images li WHERE li.listing_id = l.id
                   ORDER BY li.sort_order, li.id LIMIT 1) AS listing_image
           FROM conversations c
           LEFT JOIN listings l ON l.id = c.listing_id
           LEFT JOIN profiles gp ON gp.user_id = c.donor_id
           LEFT JOIN profiles tp ON tp.user_id = c.recipient_id
           JOIN users g ON g.id = c.donor_id
           JOIN users t ON t.id = c.recipient_id
           WHERE c.id = ? AND (c.donor_id = ? OR c.recipient_id = ?)""",
        (conversation_id, user_id, user_id),
    ).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["is_donor"] = item["donor_id"] == user_id
    item["other_name"] = item["recipient_name"] if item["is_donor"] else item["donor_name"]
    item["other_avatar"] = item["recipient_avatar"] if item["is_donor"] else item["donor_avatar"]
    item["other_id"] = item["recipient_id"] if item["is_donor"] else item["donor_id"]
    item["other_role"] = "Recipient" if item["is_donor"] else "Donor"
    return item


def conversation_messages(conversation_id: int) -> list[dict]:
    rows = get_db().execute(
        """SELECT m.*, u.name AS sender_name, p.avatar_url AS sender_avatar
           FROM messages m JOIN users u ON u.id = m.sender_id
           LEFT JOIN profiles p ON p.user_id = u.id
           WHERE m.conversation_id = ? ORDER BY m.created_at, m.id""",
        (conversation_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def mark_conversation_read(conversation_id: int, user_id: int) -> None:
    get_db().execute(
        """UPDATE messages SET read_at = COALESCE(read_at, ?)
           WHERE conversation_id = ? AND sender_id != ? AND read_at IS NULL""",
        (stamp(), conversation_id, user_id),
    )


def get_or_create_conversation(
    donor_id: int,
    recipient_id: int,
    listing_id: int | None = None,
    claim_id: int | None = None,
    initial_message: str | None = None,
) -> int:
    db = get_db()
    row = None
    if listing_id:
        row = db.execute(
            """SELECT id FROM conversations
               WHERE listing_id = ? AND donor_id = ? AND recipient_id = ?""",
            (listing_id, donor_id, recipient_id),
        ).fetchone()
    if row:
        conversation_id = row["id"]
        if claim_id:
            db.execute(
                "UPDATE conversations SET claim_id = COALESCE(claim_id, ?), updated_at = ? WHERE id = ?",
                (claim_id, stamp(), conversation_id),
            )
        initial_message = None
    else:
        now = stamp()
        cur = db.execute(
            """INSERT INTO conversations (listing_id, claim_id, donor_id, recipient_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (listing_id, claim_id, donor_id, recipient_id, now, now),
        )
        conversation_id = cur.lastrowid
    if initial_message:
        db.execute(
            """INSERT INTO messages (conversation_id, sender_id, body, created_at)
               VALUES (?, ?, ?, ?)""",
            (conversation_id, recipient_id, initial_message[:1500], stamp()),
        )
        db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?", (stamp(), conversation_id)
        )
    return conversation_id


# ---------------------------------------------------------------------------
# Expiration jobs (run opportunistically; no scheduler required for the demo)
# ---------------------------------------------------------------------------


def run_expirations() -> None:
    db = get_db()
    now = stamp()
    changed = False
    expired_features = db.execute(
        """SELECT id, donor_id, title, featured_until FROM listings
           WHERE is_featured = 1 AND featured_until IS NOT NULL AND featured_until < ?""",
        (now,),
    ).fetchall()
    for listing in expired_features:
        db.execute("UPDATE listings SET is_featured = 0 WHERE id = ?", (listing["id"],))
        notify(
            listing["donor_id"],
            "featured_expired",
            "Featured listing ended",
            f"Your featured placement for “{listing['title']}” has ended. The listing is still live and always free.",
            url_for("dashboard.donations"),
        )
        changed = True
    expired_ads = db.execute(
        "SELECT id FROM advertisements WHERE status = 'active' AND ends_at < ?", (now,)
    ).fetchall()
    for ad in expired_ads:
        db.execute("UPDATE advertisements SET status = 'expired' WHERE id = ?", (ad["id"],))
        changed = True
    if changed:
        db.commit()


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------


def _validate_image_candidate(file_storage) -> tuple[bool, str]:
    if not file_storage or not file_storage.filename:
        return False, "Choose an image file."
    filename = secure_filename(file_storage.filename)
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return False, "Images must be JPG, PNG or WebP."
    header = file_storage.stream.read(16)
    file_storage.stream.seek(0)
    is_jpeg = header.startswith(b"\xff\xd8\xff")
    is_png = header.startswith(b"\x89PNG\r\n\x1a\n")
    is_webp = header.startswith(b"RIFF") and header[8:12] == b"WEBP"
    if not (is_jpeg or is_png or is_webp):
        return False, "That file does not look like a valid image."
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > 5 * 1024 * 1024:
        return False, "Each image must be 5 MB or smaller."
    return True, extension


def save_image_uploads(files: list) -> tuple[list[str], str | None]:
    """Validate all files first, then persist them to static/uploads."""
    candidates = [f for f in files if f and f.filename]
    if not candidates:
        return [], None
    validated: list[tuple[object, str]] = []
    for file_storage in candidates:
        valid, result = _validate_image_candidate(file_storage)
        if not valid:
            return [], result
        validated.append((file_storage, result))
    saved: list[str] = []
    for file_storage, extension in validated:
        filename = f"{uuid.uuid4().hex}.{extension}"
        target = UPLOAD_DIR / filename
        try:
            file_storage.save(target)
            saved.append(f"/static/uploads/{filename}")
        except OSError:
            for path in saved:
                try:
                    (BASE_DIR / path.lstrip("/")).unlink(missing_ok=True)
                except OSError:
                    pass
            return [], "The image could not be saved. Please try again."
    return saved, None


def save_avatar(file_storage) -> tuple[str | None, str | None]:
    if not file_storage or not file_storage.filename:
        return None, None
    valid, result = _validate_image_candidate(file_storage)
    if not valid:
        return None, result
    extension = result
    filename = f"avatar-{uuid.uuid4().hex}.{extension}"
    try:
        file_storage.save(UPLOAD_DIR / filename)
    except OSError:
        return None, "The profile photo could not be saved."
    return f"/static/uploads/{filename}", None


# ---------------------------------------------------------------------------
# Partnered Delivery quotes
# ---------------------------------------------------------------------------


DELIVERY_FEE_MIN = 50.0
DELIVERY_FEE_MAX = 150.0
DELIVERY_SIZE_BASE = {"small": 32.0, "medium": 45.0, "large": 62.0}
DELIVERY_SIZE_FACTOR = {"small": 2.4, "medium": 2.8, "large": 3.1}
DELIVERY_SIZE_PARTNER = {
    "small": "lalamove",
    "medium": "jnt-express",
    "large": "metro-haul",
}


def delivery_quote(listing: dict, recipient: dict | None = None) -> dict:
    """Return an inclusive Partnered Delivery fee between ₱50 and ₱150.

    The fee varies with item size and the straight-line distance between the
    donor's area and the recipient's saved city. There are no add-on charges.
    """
    size = listing.get("item_size") or "medium"
    if size not in DELIVERY_SIZE_BASE:
        size = "medium"
    destination = None
    if recipient and recipient.get("latitude") and recipient.get("longitude"):
        destination = (recipient["latitude"], recipient["longitude"])
    if destination:
        distance = haversine_km((listing["latitude"], listing["longitude"]), destination)
    else:
        distance = 7.0
    distance = max(round(float(distance), 1), 1.5)
    billable_distance = min(distance, 30.0)
    raw_fee = DELIVERY_SIZE_BASE[size] + DELIVERY_SIZE_FACTOR[size] * billable_distance
    fee = round(raw_fee / 5) * 5
    fee = max(DELIVERY_FEE_MIN, min(DELIVERY_FEE_MAX, float(fee)))
    partner = get_db().execute(
        "SELECT * FROM delivery_partners WHERE slug = ? AND active = 1",
        (DELIVERY_SIZE_PARTNER[size],),
    ).fetchone()
    if partner is None:
        partner = get_db().execute(
            "SELECT * FROM delivery_partners WHERE active = 1 ORDER BY id LIMIT 1"
        ).fetchone()
    if size == "large":
        eta = "Same day, 2–4 hours"
    elif size == "medium":
        eta = "Same day, 1–3 hours"
    else:
        eta = "45–90 minutes"
    return {
        "distance_km": distance,
        "fee": fee,
        "fee_min": DELIVERY_FEE_MIN,
        "fee_max": DELIVERY_FEE_MAX,
        "item_size": size,
        "partner_id": partner["id"] if partner else None,
        "partner_name": partner["name"] if partner else "Partnered Delivery",
        "service_type": partner["service_type"] if partner else "Partnered courier",
        "eta": eta,
        "method_label": "Partnered Delivery",
    }


def new_tracking_code() -> str:
    return "AI-" + secrets.token_hex(3).upper()


def get_active_partners() -> list[dict]:
    return [
        dict(row)
        for row in get_db().execute(
            "SELECT * FROM delivery_partners WHERE active = 1 ORDER BY id"
        ).fetchall()
    ]


# ---------------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------------


def condition_tone(condition: str | None) -> str:
    return CONDITION_TONE.get(condition or "", "neutral")


def status_tone(status: str | None) -> str:
    return {
        "available": "success",
        "reserved": "warm",
        "claimed": "neutral",
        "unavailable": "neutral",
        "pending": "warm",
        "accepted": "success",
        "completed": "cyan",
        "rejected": "danger",
        "cancelled": "neutral",
        "open": "danger",
        "resolved": "success",
        "dismissed": "neutral",
        "active": "success",
        "paused": "warm",
        "expired": "neutral",
        "requested": "warm",
        "request_accepted": "warm",
        "awaiting_dispatch": "warm",
        "in_progress": "cyan",
        "arriving_soon": "cyan",
        "delivered": "success",
        "unpaid": "warm",
        "demo_paid": "success",
        "under_review": "warm",
        "in_progress": "warm",
        "closed": "neutral",
        "urgent": "danger",
        "high": "danger",
        "medium": "warm",
        "low": "neutral",
    }.get(status or "", "neutral")


def priority_tone(priority: str | None) -> str:
    return {
        "urgent": "danger",
        "high": "danger",
        "medium": "warm",
        "low": "neutral",
    }.get(priority or "", "neutral")


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value or secrets.token_hex(4)


def create_demo_tracking_code() -> str:
    """Backward-compatible alias for the tracking code helper."""
    return new_tracking_code()
