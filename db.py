"""Database setup and sample seed data for Anti-Imbak.

The application uses SQLite so the marketplace can run locally without external
services. Every visible number is derived from this database.
"""
from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = BASE_DIR / "schema.sql"
DATABASE_PATH = BASE_DIR / "instance" / "antiimbak.db"

LOCATION_COORDS = {
    "Quezon City": (14.6760, 121.0437),
    "Makati City": (14.5547, 121.0244),
    "Pasig City": (14.5764, 121.0851),
    "Taguig City": (14.5176, 121.0509),
    "Manila": (14.5995, 120.9842),
    "Caloocan City": (14.6488, 120.9666),
    "Marikina City": (14.6507, 121.1029),
    "Parañaque City": (14.4793, 121.0198),
    "Las Piñas City": (14.4445, 120.9939),
    "Mandaluyong City": (14.5794, 121.0359),
    "San Juan City": (14.6019, 121.0355),
    "Muntinlupa City": (14.4081, 121.0415),
    "Valenzuela City": (14.7011, 120.9830),
    "Antipolo City": (14.5878, 121.1761),
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def stamp(value: datetime | None = None) -> str:
    return (value or utcnow()).strftime("%Y-%m-%d %H:%M:%S")


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return round(radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value)), 1)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(force: bool = False) -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if force and DATABASE_PATH.exists():
        DATABASE_PATH.unlink()
    conn = connect()
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count == 0:
            seed(conn)
        conn.commit()
    finally:
        conn.close()


def seed(conn: sqlite3.Connection) -> None:
    now = utcnow()

    categories = [
        ("Electronics", "electronics", "monitor", "Phones, laptops, audio and useful tech.", 1),
        ("Furniture", "furniture", "armchair", "Home and office pieces that still have life.", 2),
        ("Clothing", "clothing", "shirt", "Clean apparel and wearable accessories.", 3),
        ("Home Appliances", "home-appliances", "fridge", "Working, repairable and nonfunctional appliances.", 4),
        ("Books & School Supplies", "books-school-supplies", "book", "Books, learning tools and school essentials.", 5),
        ("Toys & Games", "toys-games", "gamepad", "Play, imagination and family fun.", 6),
        ("Sports Equipment", "sports-equipment", "dumbbell", "Gear for movement, fitness and the outdoors.", 7),
        ("Kitchenware", "kitchenware", "utensils", "Cookware, dinnerware and kitchen helpers.", 8),
        ("Other Items", "other-items", "box", "Useful things that do not fit a box.", 9),
    ]
    conn.executemany(
        "INSERT INTO categories (name, slug, icon, description, sort_order) VALUES (?, ?, ?, ?, ?)",
        categories,
    )
    category_ids = {
        row["slug"]: row["id"]
        for row in conn.execute("SELECT id, slug FROM categories").fetchall()
    }

    users = [
        ("Aria Santos", "admin@antiimbak.com", "Aria123!", "admin", "Makati City", "aria.jpg", "0917 555 0101", "Keeping the marketplace safe and useful for every community.", 1, 240),
        ("Maya Reyes", "maya@antiimbak.com", "Maya123!", "user", "Quezon City", "maya.jpg", "0917 555 0124", "Designer, plant parent and occasional declutterer. I prefer messages before a claim so we can talk honestly about condition.", 1, 188),
        ("Noah Cruz", "noah@example.com", "Noah123!", "user", "Makati City", "noah.jpg", "0917 555 0188", "Cyclist and weekend tinkerer. I list what I no longer use and explain every fault.", 1, 151),
        ("Lina Villanueva", "lina@example.com", "Lina123!", "user", "Pasig City", "lina.jpg", "0917 555 0142", "Teacher, reader and community volunteer. I often pass things on for neighbours setting up homes.", 1, 133),
        ("Josh Mendoza", "josh@antiimbak.com", "Josh123!", "user", "Taguig City", "josh.jpg", "0917 555 0109", "Setting up a first apartment one kind handover at a time. I always ask about condition before claiming.", 0, 42),
        ("Bea Navarro", "bea@example.com", "Bea123!", "user", "Manila", "bea.jpg", "0917 555 0166", "Always happy to pass good finds forward. I document flaws so nobody travels for a surprise.", 1, 96),
        ("Miguel Torres", "miguel@example.com", "Miguel123!", "user", "Caloocan City", "miguel.jpg", "0917 555 0172", "Repairing, reusing and reducing waste whenever I can. Happy to answer repair questions.", 0, 22),
    ]
    for name, email, password, role, city, avatar, contact, bio, verified, days_ago in users:
        created = stamp(now - timedelta(days=days_ago))
        cur = conn.execute(
            """INSERT INTO users (name, email, password_hash, role, email_verified, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, email, generate_password_hash(password), role, verified, created),
        )
        lat, lon = LOCATION_COORDS[city]
        conn.execute(
            """INSERT INTO profiles
               (user_id, avatar_url, contact_number, location, city, latitude, longitude, bio, verified, member_since)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (cur.lastrowid, f"/static/img/avatars/{avatar}", contact, city, city, lat, lon, bio, verified, created),
        )
    user_ids = {
        row["email"]: row["id"] for row in conn.execute("SELECT id, email FROM users")
    }

    listings = [
        {
            "title": "Acer Aspire 5 laptop — i5, 8GB RAM, 256GB SSD",
            "category": "electronics", "donor": "maya@antiimbak.com",
            "condition": "Like New", "size": "medium", "city": "Quezon City", "area": "Diliman",
            "description": "Bought in 2023 for online classes and light design work. The lid has two shallow scratches near the hinge and the palm rest is slightly shiny from use. Screen has no dead pixels. Battery lasts around two hours, so keep the charger nearby. Original 65W charger and a sleeve are included. I am giving it away because I now use an office-issued laptop.",
            "featured": "premium", "days_ago": 1.2, "views": 218,
            "images": [("laptop-used.jpg", "Acer laptop open on a wooden table at home"), ("laptop-scratches.jpg", "Close-up of light scratches on the laptop lid")],
        },
        {
            "title": "Mesh office chair — adjustable, one armrest wobbly",
            "category": "furniture", "donor": "noah@example.com",
            "condition": "Good", "size": "medium", "city": "Makati City", "area": "Poblacion",
            "description": "Used daily for about two years in a home office. Height adjustment and tilt still work, and the mesh seat has no tears. The left armrest has a slight wobble that a screwdriver can tighten. Casters roll well and the gas lift holds my weight at 78kg. Pickup from the ground floor of our building; bring a helper if you can.",
            "featured": "featured", "days_ago": 3.1, "views": 154,
            "images": [("chair-used.jpg", "Black mesh office chair in a lived-in home office")],
        },
        {
            "title": "Two-seater fabric sofa — cat scratches on one arm",
            "category": "furniture", "donor": "lina@example.com",
            "condition": "Fair", "size": "large", "city": "Pasig City", "area": "Kapitolyo",
            "description": "A compact sofa from our old apartment. The frame is solid and the cushions still feel firm, but the right arm has visible cat scratches and a small coffee mark on the back. We are moving and cannot bring it. A cover would hide most of the damage. Measurements are 148cm wide, 82cm deep and 78cm high. Please plan for two people when moving it.",
            "featured": None, "days_ago": 5.4, "views": 79,
            "images": [("sofa-worn.jpg", "Two-seater sofa with visible wear in a small living room"), ("sofa-arm-worn.jpg", "Close-up of cat scratches on the sofa arm")],
        },
        {
            "title": "Box of Filipino novels and nursing reviewers",
            "category": "books-school-supplies", "donor": "bea@example.com",
            "condition": "Good", "size": "medium", "city": "Quezon City", "area": "Teachers Village",
            "description": "Around 22 books from my sister's college years: Dekada '70, several Bob Ong titles, a worn Merriam-Webster dictionary and a set of nursing review books from 2018. Some pages have highlights and the review books have handwritten notes. A few covers are bent at the corner. Best for a student, a barangay reading shelf or anyone who does not mind annotated books.",
            "featured": None, "days_ago": 6.8, "views": 112,
            "images": [("books-used.jpg", "Used paperback novels and reviewers stacked on a table")],
        },
        {
            "title": "Preloved office clothes bundle — size M",
            "category": "clothing", "donor": "maya@antiimbak.com",
            "condition": "Good", "size": "small", "city": "Taguig City", "area": "BGC",
            "description": "Eight pieces that have been washed and stored in a smoke-free home: three plain blouses, two button-up shirts, one pair of black trousers and two casual dresses. No holes or broken zippers. The black trousers have a faint shine at the knees and one blouse is missing its top button. Good for interviews or daily office wear, not formal events.",
            "featured": None, "days_ago": 2.3, "views": 63,
            "images": [("clothes-bundle.jpg", "Neatly folded preloved office clothing on a bed")],
        },
        {
            "title": "Front-load washing machine — leaking gasket, for repair",
            "category": "home-appliances", "donor": "miguel@example.com",
            "condition": "For Repair", "size": "large", "city": "Caloocan City", "area": "Grace Park",
            "description": "7kg front-load machine. It fills, washes and spins, but the door gasket leaks during the spin cycle. I replaced the gasket once and the leak came back, so there may be a bent door rim. Listing it for a repair hobbyist or technician, not for immediate household use. The drum is clean and the control board works. I can send the service manual photos through Messages.",
            "featured": None, "days_ago": 4.4, "views": 91,
            "images": [("washer-used.jpg", "Front-load washing machine in a covered laundry area"), ("washer-gasket.jpg", "Close-up of the worn door gasket")],
        },
        {
            "title": "20L microwave — heats well, keypad needs a firm press",
            "category": "home-appliances", "donor": "noah@example.com",
            "condition": "Good", "size": "medium", "city": "Manila", "area": "Sampaloc",
            "description": "Used in a boarding-house kitchen for three years. It still heats evenly on high and the turntable turns smoothly. The start button sometimes needs two presses and the white casing has yellowed slightly. Waveguide cover is intact. No rust inside. It is around 11kg, so please bring a sturdy bag or cart if you collect it.",
            "featured": None, "days_ago": 8.2, "views": 57,
            "images": [("microwave-used.jpg", "White microwave on a small kitchen counter")],
        },
        {
            "title": "Wooden blocks and shape sorter — complete set",
            "category": "toys-games", "donor": "maya@antiimbak.com",
            "condition": "Good", "size": "small", "city": "Quezon City", "area": "Cubao",
            "description": "A wooden play set for ages 2 to 5. All 24 blocks, the shape sorter and the cotton storage bag are included. Corners are smooth and there are no splinters. Some blocks have faded paint from years of play. My nephew has outgrown it, and our barangay reading corner asked for safe toys like these.",
            "featured": None, "days_ago": 0.7, "views": 34, "status": "reserved",
            "images": [("toys-used.jpg", "Wooden play blocks and shape sorter on a mat")],
        },
        {
            "title": "Mountain bike — 26er, brakes need adjustment",
            "category": "sports-equipment", "donor": "josh@antiimbak.com",
            "condition": "Fair", "size": "large", "city": "Pasig City", "area": "Ortigas Center",
            "description": "A 26-inch mountain bike with a steel frame and 21-speed groupset. It has rust spots on the chain and the rear brake cable is sticky, so it should be checked by a bike mechanic before riding on the road. Tires hold air and both wheels are true. The saddle has a small tear. Frame fits riders around 5'5\" to 5'10\". Please inspect carefully; I would not call it road-ready yet.",
            "featured": "featured", "days_ago": 1.8, "views": 183,
            "images": [("bike-used.jpg", "Mountain bike leaning against a concrete wall"), ("bike-brakes.jpg", "Rusty chain and rear brake area of the bicycle")],
        },
        {
            "title": "Acoustic guitar — beginner model, new strings",
            "category": "other-items", "donor": "bea@example.com",
            "condition": "Good", "size": "medium", "city": "Manila", "area": "Ermita",
            "description": "Full-size acoustic guitar from a local music shop. New strings installed in July and action adjusted at the same time. There is a small ding on the lower edge and the pickguard has light scratches, but it stays in tune and sounds warm. Includes a padded gig bag and capo. I am passing it on after moving to a smaller apartment.",
            "featured": None, "days_ago": 24, "views": 201, "status": "claimed",
            "images": [("guitar-used.jpg", "Acoustic guitar on a worn chair in a bedroom")],
        },
        {
            "title": "24-inch IPS monitor — VGA and HDMI, no dead pixels",
            "category": "electronics", "donor": "lina@example.com",
            "condition": "Like New", "size": "medium", "city": "Taguig City", "area": "Uptown",
            "description": "A clean 24-inch 1080p monitor used for two years at a school office. No dead pixels or screen scratches. Original stand, power cable and one HDMI cable are included. The VGA port has a loose plastic lip but works when the cable is seated properly. I switched to a laptop-only setup and would like it to help someone study or work.",
            "featured": None, "days_ago": 2.9, "views": 86, "status": "reserved",
            "images": [("monitor-used.jpg", "Monitor on a study desk in a small apartment")],
        },
        {
            "title": "Kitchen starter set — pot, pan, plates and utensils",
            "category": "kitchenware", "donor": "bea@example.com",
            "condition": "Good", "size": "large", "city": "Quezon City", "area": "Project 4",
            "description": "A practical set for someone moving into a first place: a medium pot with lid, a nonstick frying pan with light coating wear, a mixing bowl, wooden spoons, four plates, two mugs and a small knife block with three knives. Everything is clean and functional. The nonstick pan should be replaced soon if you cook often, but it still works with a little oil.",
            "featured": None, "days_ago": 7.1, "views": 72,
            "images": [("kitchen-used.jpg", "Used kitchen basics spread out on a counter")],
        },
        {
            "title": "Running shoes — US 8, sole starting to separate",
            "category": "sports-equipment", "donor": "maya@antiimbak.com",
            "condition": "Fair", "size": "small", "city": "Makati City", "area": "Bel-Air",
            "description": "US size 8 neutral running shoes. The upper is clean and there is plenty of tread left, but the right sole is starting to lift at the toe. A shoe repair shop can glue it for a small fee. I used them for light walks only after the separation started, not for running. Listed honestly because this is not a race-ready pair.",
            "featured": None, "days_ago": 0.3, "views": 29,
            "images": [("shoes-used.jpg", "Running shoes with light wear on a concrete step")],
        },
        {
            "title": "Adjustable dumbbells — 10kg pair with plates",
            "category": "sports-equipment", "donor": "noah@example.com",
            "condition": "Good", "size": "large", "city": "Pasig City", "area": "Kapitolyo",
            "description": "Pair of adjustable dumbbells with plates up to 10kg per side. No rust on the bars and all locking collars are included. Some plates have paint chips from being stored under a bed. I moved to a gym routine and no longer need them at home. They are heavy, so a sturdy bag or small cart helps.",
            "featured": None, "days_ago": 3.8, "views": 122, "status": "reserved",
            "images": [("dumbbells-used.jpg", "Adjustable dumbbells beside a yoga mat")],
        },
        {
            "title": "School backpack and partly used notebooks",
            "category": "books-school-supplies", "donor": "lina@example.com",
            "condition": "Fair", "size": "small", "city": "Manila", "area": "Paco",
            "description": "A grey backpack with working zippers and padded straps. The bottom has a small scuff and the front pocket lining is torn, but it still carries books safely. Bundle includes three notebooks with around 20 used pages, a pack of pencils, two rulers and a pencil case. Best for a student who can reuse the remaining pages.",
            "featured": None, "days_ago": 1.1, "views": 47, "status": "reserved",
            "images": [("backpack-used.jpg", "Used school backpack and notebooks on a bench")],
        },
        {
            "title": "Study lamp — switch flickers, for repair",
            "category": "other-items", "donor": "miguel@example.com",
            "condition": "For Repair", "size": "small", "city": "Caloocan City", "area": "Bagong Barrio",
            "description": "Metal desk lamp with a warm LED bulb. The base is stable and the arm holds its position, but the inline switch flickers and sometimes needs wiggling. I have not opened the wiring and would not use it unattended until the switch is replaced. Suitable for someone comfortable with basic electrical repair. Bulb is included.",
            "featured": None, "days_ago": 5.9, "views": 33,
            "images": [("lamp-used.jpg", "Metal study lamp on a wooden desk at night")],
        },
        {
            "title": "Epson L3110 printer — clogged head, no power cable",
            "category": "electronics", "donor": "noah@example.com",
            "condition": "Nonfunctional", "size": "medium", "city": "Quezon City", "area": "New Manila",
            "description": "Nonfunctional unit for parts or repair. The printhead is badly clogged after months in storage and the power cable is missing. Do not plug it in with a random adapter; it needs the correct Epson adapter. Paper feed rollers turn by hand and the scanner glass is intact. The ink tanks are empty. I am listing it only because repairers often need these parts.",
            "featured": None, "days_ago": 4.7, "views": 64,
            "images": [("printer-clog.jpg", "Used Epson printer with missing power cable")],
        },
        {
            "title": "Fabric armchair — faded and stained, cover recommended",
            "category": "furniture", "donor": "bea@example.com",
            "condition": "Fair", "size": "large", "city": "Makati City", "area": "Forbes Park",
            "description": "Comfortable fabric armchair with a gently curved back. The fabric has faded on the sunny side and there is a coffee stain on the seat. The frame is solid and the cushion still holds its shape. A slipcover would refresh it. I am holding it for a neighbour until the weekend, so it is marked unavailable for now.",
            "featured": None, "days_ago": 9.6, "views": 101, "status": "unavailable",
            "images": [("armchair-worn.jpg", "Faded fabric armchair near a bright window")],
        },
    ]

    featured_packages = {
        "featured": {"fee": 149.0, "days": 14, "label": "Featured Listing"},
        "premium": {"fee": 399.0, "days": 30, "label": "Premium Boost"},
    }
    listing_ids: dict[str, int] = {}
    for index, item in enumerate(listings):
        donor_id = user_ids[item["donor"]]
        base_lat, base_lon = LOCATION_COORDS[item["city"]]
        jitter = (index % 7 - 3) * 0.0021
        latitude = round(base_lat + jitter, 6)
        longitude = round(base_lon - jitter * 0.7, 6)
        created = stamp(now - timedelta(days=item["days_ago"]))
        featured = item.get("featured")
        featured_until = None
        if featured:
            featured_until = stamp(now + timedelta(days=featured_packages[featured]["days"] - min(item["days_ago"], 3)))
        cur = conn.execute(
            """INSERT INTO listings
               (donor_id, category_id, title, description, condition, item_size, city, area,
                latitude, longitude, status, is_featured, featured_until, views, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                donor_id, category_ids[item["category"]], item["title"], item["description"],
                item["condition"], item["size"], item["city"], item["area"], latitude, longitude,
                item.get("status", "available"), 1 if featured else 0, featured_until,
                item["views"], created, created,
            ),
        )
        listing_id = cur.lastrowid
        listing_ids[item["title"]] = listing_id
        for sort_order, (filename, alt_text) in enumerate(item["images"]):
            conn.execute(
                "INSERT INTO listing_images (listing_id, image_url, alt_text, sort_order) VALUES (?, ?, ?, ?)",
                (listing_id, f"/static/img/{filename}", alt_text, sort_order),
            )
        if featured:
            pkg = featured_packages[featured]
            starts = now - timedelta(days=min(item["days_ago"], 2))
            ends = now + timedelta(days=pkg["days"] - min(item["days_ago"], 3))
            tx = conn.execute(
                """INSERT INTO transactions
                   (user_id, type, reference_type, reference_id, amount, platform_fee, provider_payout,
                    payment_method, description, status, created_at)
                   VALUES (?, 'featured', 'listing', ?, ?, ?, 0, 'Promotion record', ?, 'completed', ?)""",
                (donor_id, listing_id, pkg["fee"], pkg["fee"], f"{pkg['label']} — {item['title']}", stamp(starts)),
            )
            conn.execute(
                """INSERT INTO featured_listings
                   (listing_id, donor_id, package, amount, starts_at, ends_at, transaction_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (listing_id, donor_id, featured, pkg["fee"], stamp(starts), stamp(ends), tx.lastrowid, stamp(starts)),
            )

    # One ended promotion so the expiry path and ledger have history.
    historical_title = "20L microwave — heats well, keypad needs a firm press"
    historical_id = listing_ids[historical_title]
    historical_start = now - timedelta(days=40)
    historical_end = now - timedelta(days=26)
    hist_tx = conn.execute(
        """INSERT INTO transactions
           (user_id, type, reference_type, reference_id, amount, platform_fee, provider_payout,
            payment_method, description, status, created_at)
           VALUES (?, 'featured', 'listing', ?, 149, 149, 0, 'Promotion record', ?, 'completed', ?)""",
        (user_ids["noah@example.com"], historical_id, f"Featured Listing — {historical_title}", stamp(historical_start)),
    )
    conn.execute(
        """INSERT INTO featured_listings
           (listing_id, donor_id, package, amount, starts_at, ends_at, transaction_id, created_at)
           VALUES (?, ?, 'featured', 149, ?, ?, ?, ?)""",
        (historical_id, user_ids["noah@example.com"], stamp(historical_start), stamp(historical_end), hist_tx.lastrowid, stamp(historical_start)),
    )

    partners = [
        ("Lalamove", "lalamove", "Motorcycle courier", "45–90 minutes", "Small parcels and pouches."),
        ("J&T Express", "jnt-express", "Same-day courier", "1–3 hours", "Boxed electronics and medium items."),
        ("Metro Haul", "metro-haul", "Local moving service", "2–4 hours", "Furniture and bulky items with a helper."),
    ]
    conn.executemany(
        "INSERT INTO delivery_partners (name, slug, service_type, eta, description) VALUES (?, ?, ?, ?, ?)",
        partners,
    )
    partner_ids = {
        row["slug"]: row["id"] for row in conn.execute("SELECT id, slug FROM delivery_partners")
    }

    claim_rows = [
        {
            "listing": "Acer Aspire 5 laptop — i5, 8GB RAM, 256GB SSD",
            "claimant": "bea@example.com",
            "message": "Hi Maya. I am a third-year design student sharing one laptop with my younger sister. The Acer would let me finish plates without borrowing a library computer after class. I asked about the battery in Messages and I am fine with the two-hour estimate. Could we use Partnered Delivery to Manila?",
            "method": "delivery", "address": "9th Street, Barangay 659, Manila", "days_ago": 0.8,
            "status": "pending", "fee": 85, "partner": "jnt-express", "tracking": "AI-7K2MB9",
        },
        {
            "listing": "Acer Aspire 5 laptop — i5, 8GB RAM, 256GB SSD",
            "claimant": "miguel@example.com",
            "message": "I run a small laptop repair stall in Cubao and could give this machine a proper clean-up before passing it to a student on my waiting list. I can collect it myself from a public place and show you the repair receipt. No payment expected.",
            "method": "pickup", "address": None, "days_ago": 0.5, "status": "pending",
        },
        {
            "listing": "Preloved office clothes bundle — size M",
            "claimant": "lina@example.com",
            "message": "I volunteer with a women's shelter in Pasig. These pieces would go to two residents preparing for interviews. We can take Partnered Delivery or I can meet you in BGC. I will send photos of the handover if the shelter allows it.",
            "method": "delivery", "address": "Barangay San Antonio, Pasig City", "days_ago": 1.4,
            "status": "pending", "fee": 65, "partner": "lalamove", "tracking": "AI-4Q8L1C",
        },
        {
            "listing": "Wooden blocks and shape sorter — complete set",
            "claimant": "miguel@example.com",
            "message": "Our barangay reading corner is starting a small play shelf for toddlers. The complete wooden set would be perfect and I can send a photo once it is set up. We chose Partnered Delivery to Caloocan because I do not have a car this week.",
            "method": "delivery", "address": "Grace Park, Caloocan City", "days_ago": 0.4,
            "status": "accepted", "handover": 1, "fee": 75, "partner": "lalamove",
            "tracking": "AI-1M5T7A", "delivery": "awaiting_dispatch",
            "donor_note": "The reading corner sounds lovely. I have confirmed the handover plan and will pack the blocks today.",
        },
        {
            "listing": "Two-seater fabric sofa — cat scratches on one arm",
            "claimant": "josh@antiimbak.com",
            "message": "I am furnishing a first apartment and have a small living room. The sofa would make the space feel like home, and I have seen the photos of the scratches. I can arrange a moving helper if the delivery partner needs one.",
            "method": "delivery", "address": "Ususan, Taguig City", "days_ago": 4.0,
            "status": "rejected", "fee": 120, "partner": "metro-haul", "tracking": "AI-9R3W2D",
            "delivery": "cancelled", "donor_note": "So sorry — a neighbour has already asked for this one and can carry it out this weekend.",
        },
        {
            "listing": "Front-load washing machine — leaking gasket, for repair",
            "claimant": "josh@antiimbak.com",
            "message": "Our shared apartment has been hand-washing clothes for months. My uncle is a technician and can replace the gasket, but I want to be clear that I understand the leak. We chose Partnered Delivery to Taguig. Please let me know if the door rim looks bent.",
            "method": "delivery", "address": "Ususan, Taguig City", "days_ago": 1.9,
            "status": "pending", "fee": 135, "partner": "metro-haul", "tracking": "AI-6H1N4P",
        },
        {
            "listing": "Adjustable dumbbells — 10kg pair with plates",
            "claimant": "josh@antiimbak.com",
            "message": "I am building a small home workout corner and cannot afford weights right now. I chose Self Pickup because my brother can help me carry them from Pasig on Saturday. I will check the collars before we leave.",
            "method": "pickup", "address": None, "days_ago": 2.2,
            "status": "accepted", "handover": 1,
            "donor_note": "Saturday works. Let's meet at the lobby and I will show you that every collar is there.",
        },
        {
            "listing": "Acoustic guitar — beginner model, new strings",
            "claimant": "josh@antiimbak.com",
            "message": "I have wanted to learn guitar for years and recently joined a free community music class. This would let me practise between sessions. I chose Partnered Delivery to Taguig and will send a photo when I learn my first song.",
            "method": "delivery", "address": "Ususan, Taguig City", "days_ago": 20,
            "status": "completed", "handover": 1, "fee": 130, "partner": "jnt-express",
            "tracking": "AI-3J8V5X", "delivery": "delivered",
        },
        {
            "listing": "20L microwave — heats well, keypad needs a firm press",
            "claimant": "bea@example.com",
            "message": "Our small student dorm has no way to reheat meals. A microwave would be shared by four students. I asked about the keypad and can live with pressing twice. Partnered Delivery to Manila is easiest because none of us has a car.",
            "method": "delivery", "address": "Sampaloc, Manila", "days_ago": 0.6,
            "status": "pending", "fee": 80, "partner": "jnt-express", "tracking": "AI-2B7G9M",
        },
        {
            "listing": "24-inch IPS monitor — VGA and HDMI, no dead pixels",
            "claimant": "bea@example.com",
            "message": "I need a larger screen for online tutoring and my old monitor has a flickering backlight. I have read the note about the loose VGA lip and will use HDMI. Partnered Delivery to Manila works for me.",
            "method": "delivery", "address": "Ermita, Manila", "days_ago": 2.4,
            "status": "accepted", "handover": 1, "fee": 95, "partner": "jnt-express",
            "tracking": "AI-8D4F2K", "delivery": "in_progress",
            "donor_note": "Accepted. The monitor is boxed with the HDMI cable and the Donor has confirmed the handover plan.",
        },
        {
            "listing": "School backpack and partly used notebooks",
            "claimant": "josh@antiimbak.com",
            "message": "My younger cousin is starting Grade 7 and needs a bag. The torn pocket does not bother us because I can sew it. We chose Partnered Delivery to Taguig so it arrives before enrolment.",
            "method": "delivery", "address": "Ususan, Taguig City", "days_ago": 3.1,
            "status": "accepted", "handover": 1, "fee": 70, "partner": "lalamove",
            "tracking": "AI-5C9N1R", "delivery": "arriving_soon",
            "donor_note": "Confirmed. The bag is packed with the notebooks and the delivery is on its way.",
        },
        {
            "listing": "Mountain bike — 26er, brakes need adjustment",
            "claimant": "bea@example.com",
            "message": "I would like to restore this for a community bike-to-school group. I understand the brakes are not road-ready and will have a mechanic check them first. Partnered Delivery would be difficult for a bike, so I chose Self Pickup and can bring a friend with a van.",
            "method": "pickup", "address": None, "days_ago": 0.2, "status": "pending",
        },
    ]

    claim_ids: dict[tuple[str, str], int] = {}
    for row in claim_rows:
        listing_id = listing_ids[row["listing"]]
        claimant_id = user_ids[row["claimant"]]
        created = stamp(now - timedelta(days=row["days_ago"]))
        cur = conn.execute(
            """INSERT INTO claims
               (listing_id, claimant_id, message, receive_method, delivery_address, status,
                donor_note, handover_confirmed, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                listing_id, claimant_id, row["message"], row["method"], row.get("address"),
                row["status"], row.get("donor_note"), row.get("handover", 0), created, created,
            ),
        )
        claim_id = cur.lastrowid
        claim_ids[(row["listing"], row["claimant"])] = claim_id
        if row["method"] == "delivery":
            conn.execute(
                """INSERT INTO delivery_requests
                   (claim_id, listing_id, requester_id, partner_id, pickup_address, dropoff_address,
                    distance_km, fee, status, tracking_code, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    claim_id, listing_id, claimant_id, partner_ids[row["partner"]],
                    f"{row['listing'] and [l for l in listings if l['title'] == row['listing']][0]['area']}, "
                    f"{[l for l in listings if l['title'] == row['listing']][0]['city']}",
                    row["address"], 0.0, float(row["fee"]), row.get("delivery", "request_accepted"),
                    row["tracking"], created, created,
                ),
            )
    # Refresh distance values with the same coordinates used above.
    for delivery in conn.execute(
        """SELECT d.id, d.distance_km, l.latitude, l.longitude, d.requester_id,
                  p.latitude AS requester_lat, p.longitude AS requester_lon
           FROM delivery_requests d JOIN listings l ON l.id = d.listing_id
           JOIN profiles p ON p.user_id = d.requester_id"""
    ).fetchall():
        distance = haversine_km(
            (delivery["latitude"], delivery["longitude"]),
            (delivery["requester_lat"], delivery["requester_lon"]),
        )
        conn.execute(
            "UPDATE delivery_requests SET distance_km = ? WHERE id = ?",
            (max(round(distance, 1), 1.5), delivery["id"]),
        )

    # The accepted and completed examples need matching listing states.
    conn.execute(
        "UPDATE listings SET status = 'reserved' WHERE id IN (?, ?, ?, ?)",
        (
            listing_ids["Wooden blocks and shape sorter — complete set"],
            listing_ids["Adjustable dumbbells — 10kg pair with plates"],
            listing_ids["24-inch IPS monitor — VGA and HDMI, no dead pixels"],
            listing_ids["School backpack and partly used notebooks"],
        ),
    )
    conn.execute(
        "UPDATE listings SET status = 'claimed' WHERE id = ?",
        (listing_ids["Acoustic guitar — beginner model, new strings"],),
    )

    # Delivery ledger entry for the completed guitar.
    guitar_claim = claim_ids[("Acoustic guitar — beginner model, new strings", "josh@antiimbak.com")]
    guitar_delivery = conn.execute(
        "SELECT id, fee, tracking_code FROM delivery_requests WHERE claim_id = ?", (guitar_claim,)
    ).fetchone()
    conn.execute(
        """INSERT INTO transactions
           (user_id, type, reference_type, reference_id, amount, platform_fee, provider_payout,
            payment_method, description, status, created_at)
           VALUES (?, 'delivery', 'delivery_request', ?, ?, 0, ?, 'Partnered Delivery', ?, 'completed', ?)""",
        (
            user_ids["josh@antiimbak.com"], guitar_delivery["id"], guitar_delivery["fee"],
            guitar_delivery["fee"], f"Partnered Delivery fee — Acoustic guitar ({guitar_delivery['tracking_code']})",
            stamp(now - timedelta(days=19)),
        ),
    )

    # Conversations and messages.
    conversation_rows = [
        {
            "donor": "maya@antiimbak.com", "recipient": "bea@example.com",
            "listing": "Acer Aspire 5 laptop — i5, 8GB RAM, 256GB SSD",
            "messages": [
                ("bea@example.com", "Hi Maya. Is the battery still okay for school? I usually need three hours away from a socket.", 0.9, 1),
                ("maya@antiimbak.com", "Hi Bea. It lasts around two hours on a full charge. I replaced the charger last year, so bring it along for longer days.", 0.8, 1),
                ("bea@example.com", "Thank you. Are the scratches on the lid deep?", 0.7, 1),
                ("maya@antiimbak.com", "Only cosmetic. I can send a close-up before you decide.", 0.6, 1),
                ("bea@example.com", "Please do. I am also okay with Partnered Delivery to Manila if the fee stays within ₱150.", 0.5, 1),
                ("maya@antiimbak.com", "Here is the close-up. The quoted delivery is the full fee; there are no extra charges on my side.", 0.4, 1),
                ("bea@example.com", "Got it. I submitted a request. Thank you for answering everything.", 0.2, 0),
            ],
            "product_image": "laptop-scratches.jpg",
        },
        {
            "donor": "maya@antiimbak.com", "recipient": "miguel@example.com",
            "listing": "Acer Aspire 5 laptop — i5, 8GB RAM, 256GB SSD",
            "messages": [
                ("miguel@example.com", "Hi Maya, I sent a request too. I repair laptops in Cubao and can collect it myself if you prefer.", 0.4, 1),
                ("maya@antiimbak.com", "Thanks Miguel. I have another student asking as well, so let me review both requests first.", 0.3, 1),
                ("miguel@example.com", "Of course. If the student gets it, I can still check the charger for free.", 0.1, 0),
            ],
        },
        {
            "donor": "maya@antiimbak.com", "recipient": "lina@example.com",
            "listing": "Preloved office clothes bundle — size M",
            "messages": [
                ("lina@example.com", "Hi Maya, are the trousers a straight cut? Two of our shelter residents are around 5'4\".", 1.5, 1),
                ("maya@antiimbak.com", "Yes, straight cut with a little stretch. I can measure the waist and send a photo if useful.", 1.3, 1),
                ("lina@example.com", "That would help. Thank you for considering the shelter.", 1.2, 1),
                ("maya@antiimbak.com", "Waist is 30 inches and the inseam is 28. Sending a photo now.", 1.1, 0),
            ],
        },
        {
            "donor": "miguel@example.com", "recipient": "josh@antiimbak.com",
            "listing": "Front-load washing machine — leaking gasket, for repair",
            "messages": [
                ("josh@antiimbak.com", "Hi Miguel, does the leak happen during wash or only spin?", 2.0, 1),
                ("miguel@example.com", "Only during the spin cycle. It fills and drains normally, but water seeps from the bottom of the door.", 1.8, 1),
                ("josh@antiimbak.com", "My uncle can replace the gasket. Is the door rim visibly bent?", 1.6, 1),
                ("miguel@example.com", "Not visibly, but I am not a technician. I can send a photo of the rim from the inside.", 1.5, 1),
                ("josh@antiimbak.com", "Please send it. We chose Partnered Delivery because a jeepney is not realistic for this.", 1.2, 0),
            ],
            "product_image": "washer-gasket.jpg",
        },
        {
            "donor": "lina@example.com", "recipient": "josh@antiimbak.com",
            "listing": "Two-seater fabric sofa — cat scratches on one arm",
            "messages": [
                ("josh@antiimbak.com", "Hi Lina, I saw the scratch photos. Would a standard cover fit the 148cm width?", 4.2, 1),
                ("lina@example.com", "A 150cm cover should work. I am sorry the request was declined; a neighbour asked first and can carry it out this weekend.", 3.9, 1),
                ("josh@antiimbak.com", "No problem. Thank you for being clear about the condition.", 3.8, 1),
            ],
        },
        {
            "donor": "bea@example.com", "recipient": "josh@antiimbak.com",
            "listing": "Acoustic guitar — beginner model, new strings",
            "messages": [
                ("josh@antiimbak.com", "The guitar arrived safely. The capo was in the bag and the strings sound good.", 18.8, 1),
                ("bea@example.com", "Wonderful. Send me a recording when you learn your first song.", 18.4, 1),
                ("josh@antiimbak.com", "I will. Thank you again for the delivery updates.", 18.2, 1),
            ],
        },
        {
            "donor": "lina@example.com", "recipient": "bea@example.com",
            "listing": "24-inch IPS monitor — VGA and HDMI, no dead pixels",
            "messages": [
                ("bea@example.com", "Hi Lina, I will use HDMI so the loose VGA lip should not matter. Is the stand adjustable?", 2.6, 1),
                ("lina@example.com", "Only tilt, not height. I added a small wooden riser in the photo, but that stays with me.", 2.5, 1),
                ("bea@example.com", "That is fine. The delivery status says it is moving now. Thank you.", 0.6, 0),
            ],
        },
        {
            "donor": "maya@antiimbak.com", "recipient": "miguel@example.com",
            "listing": "Wooden blocks and shape sorter — complete set",
            "messages": [
                ("miguel@example.com", "The blocks are for our barangay play shelf. Are any corners chipped?", 0.8, 1),
                ("maya@antiimbak.com", "No chips, just faded paint on a few blocks. I checked all 24 pieces before packing.", 0.6, 1),
                ("miguel@example.com", "Perfect. I confirmed the delivery address with the courier details on the request.", 0.3, 0),
            ],
        },
        {
            "donor": "noah@example.com", "recipient": "bea@example.com",
            "listing": "20L microwave — heats well, keypad needs a firm press",
            "messages": [
                ("bea@example.com", "Hi Noah, does the turntable wobble at all?", 0.7, 1),
                ("noah@example.com", "No wobble. The only issue is the start button needing a firm press.", 0.5, 1),
                ("bea@example.com", "Thanks. I sent a request with Partnered Delivery to the dorm.", 0.4, 0),
            ],
        },
        {
            "donor": "josh@antiimbak.com", "recipient": "bea@example.com",
            "listing": "Mountain bike — 26er, brakes need adjustment",
            "messages": [
                ("bea@example.com", "Hi Josh, I run a bike-to-school group. Can I bring a mechanic to inspect the brakes before taking it?", 0.3, 1),
                ("josh@antiimbak.com", "Yes, please do. I would rather have it checked than have someone ride it as is.", 0.2, 1),
                ("bea@example.com", "Understood. I chose Self Pickup and can come Saturday morning.", 0.1, 0),
            ],
        },
        {
            "donor": "lina@example.com", "recipient": "josh@antiimbak.com",
            "listing": "School backpack and partly used notebooks",
            "messages": [
                ("josh@antiimbak.com", "The backpack is arriving soon, right? My cousin is excited.", 0.7, 1),
                ("lina@example.com", "Yes, the status says Arriving Soon. Please have someone ready to receive it.", 0.5, 1),
                ("josh@antiimbak.com", "My aunt is home. Thank you for packing the notebooks separately.", 0.2, 0),
            ],
        },
    ]

    conversation_ids: dict[tuple[str, str], int] = {}
    for row in conversation_rows:
        donor_id = user_ids[row["donor"]]
        recipient_id = user_ids[row["recipient"]]
        listing_id = listing_ids[row["listing"]]
        claim_id = claim_ids.get((row["listing"], row["recipient"]))
        first_at = now - timedelta(days=row["messages"][0][2])
        last_at = now - timedelta(days=row["messages"][-1][2])
        cur = conn.execute(
            """INSERT INTO conversations
               (listing_id, claim_id, donor_id, recipient_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (listing_id, claim_id, donor_id, recipient_id, stamp(first_at), stamp(last_at)),
        )
        conversation_id = cur.lastrowid
        conversation_ids[(row["donor"], row["recipient"])] = conversation_id
        for sender, body, days_ago, is_read in row["messages"]:
            sent = stamp(now - timedelta(days=days_ago))
            attachment = None
            if sender == row["recipient"] and row.get("product_image"):
                attachment = f"/static/img/{row['product_image']}"
                row["product_image"] = None
            conn.execute(
                """INSERT INTO messages
                   (conversation_id, sender_id, body, attachment_url, read_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    conversation_id, user_ids[sender], body, attachment,
                    sent if is_read else None, sent,
                ),
            )

    ad_packages = [
        ("Homepage Hero Banner", "home_banner", 1499.0, 30, "A wide, clearly labelled banner above the homepage discovery feed."),
        ("Category Spotlight", "category", 899.0, 30, "Featured placement inside a single donation category."),
        ("Sponsored Business Card", "browse_sidebar", 499.0, 30, "A compact sponsored card in the marketplace sidebar."),
    ]
    conn.executemany(
        "INSERT INTO ad_packages (name, placement, price, duration_days, description) VALUES (?, ?, ?, ?, ?)",
        ad_packages,
    )
    ad_package_ids = {
        row["placement"]: row["id"] for row in conn.execute("SELECT id, placement FROM ad_packages")
    }
    ads = [
        (
            "BrightNest Home Care", "Home cleaning", "Come home to a fresh start.",
            "Eco-friendly deep cleaning for homes, condos and move-ins across Metro Manila. Anti-Imbak neighbours get 10% off their first clean.",
            "View cleaning packages", "/sponsored/1", "/static/img/ads/cleaning.jpg",
            "home_banner", None, ad_package_ids["home_banner"], "active", 25, 1499.0,
        ),
        (
            "MoveEasy Truck Rental", "Moving & truck rental", "Moving something bulky?",
            "Self-drive and with-driver truck rentals for furniture pickups, apartment moves and donation deliveries.",
            "See truck options", "/sponsored/2", "/static/img/ads/truck.jpg",
            "browse_sidebar", None, ad_package_ids["browse_sidebar"], "active", 18, 499.0,
        ),
        (
            "Fixora Appliance Repair", "Local repair services", "Repair first. Replace less.",
            "Trusted diagnostics for small appliances. Mention Anti-Imbak and receive a free repair assessment.",
            "Explore repairs", "/sponsored/3", "/static/img/ads/repair.jpg",
            "category", category_ids["electronics"], ad_package_ids["category"], "active", 20, 899.0,
        ),
    ]
    for advertiser, biz, title, body, cta, url, image, placement, category_id, package_id, status, days_left, amount in ads:
        start = now - timedelta(days=2)
        end = now + timedelta(days=days_left)
        cur = conn.execute(
            """INSERT INTO advertisements
               (advertiser_name, business_type, title, body, cta_label, cta_url, image_url, placement,
                category_id, package_id, status, starts_at, ends_at, impressions, clicks, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                advertiser, biz, title, body, cta, url, image, placement, category_id,
                package_id, status, stamp(start), stamp(end), 0, 0, stamp(start),
            ),
        )
        if placement == "home_banner":
            conn.execute(
                """INSERT INTO transactions
                   (user_id, type, reference_type, reference_id, amount, platform_fee, provider_payout,
                    payment_method, description, status, created_at)
                   VALUES (NULL, 'advertisement', 'advertisement', ?, ?, ?, 0, 'Advertising invoice', ?, 'completed', ?)""",
                (cur.lastrowid, amount, amount, f"{advertiser} — Homepage Hero Banner", stamp(start)),
            )

    conn.execute(
        """INSERT INTO ad_inquiries
           (name, email, business_name, business_type, package_id, message, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'new', ?)""",
        (
            "Carlo Dizon", "carlo@greenhaul.ph", "GreenHaul Junk Removal", "Junk removal",
            ad_package_ids["browse_sidebar"],
            "We handle responsible junk removal and would like to reach Donors who are decluttering. Please send the media kit.",
            stamp(now - timedelta(days=1.1)),
        ),
    )

    open_report_1 = conn.execute(
        """INSERT INTO reports (reporter_id, listing_id, reported_user_id, reason, details, status, created_at)
           VALUES (?, ?, ?, ?, ?, 'open', ?)""",
        (
            user_ids["lina@example.com"], listing_ids["20L microwave — heats well, keypad needs a firm press"],
            user_ids["noah@example.com"], "Misleading description",
            "The listing says the keypad needs a firm press. I would like someone to verify that the start button still works reliably before another member travels.",
            stamp(now - timedelta(hours=16)),
        ),
    )
    open_report_2 = conn.execute(
        """INSERT INTO reports (reporter_id, listing_id, reported_user_id, reason, details, status, created_at)
           VALUES (?, ?, ?, ?, ?, 'open', ?)""",
        (
            user_ids["miguel@example.com"], listing_ids["Fabric armchair — faded and stained, cover recommended"],
            user_ids["bea@example.com"], "Unsafe transaction",
            "The listing is marked unavailable but still appears in search. Please check whether the status is showing correctly.",
            stamp(now - timedelta(hours=7)),
        ),
    )
    resolved_report = conn.execute(
        """INSERT INTO reports (reporter_id, listing_id, reported_user_id, reason, details, status, admin_note,
                                resolved_by, created_at, resolved_at)
           VALUES (?, ?, ?, ?, ?, 'resolved', ?, ?, ?, ?)""",
        (
            user_ids["bea@example.com"], historical_id, user_ids["noah@example.com"],
            "Inappropriate images", "A duplicate photo appeared in the gallery.",
            "Gallery reviewed and cleaned up. No further action needed.",
            user_ids["admin@antiimbak.com"], stamp(now - timedelta(days=6)), stamp(now - timedelta(days=5)),
        ),
    )

    dispute_rows = [
        {
            "code": "DSP-2041", "reporter": "bea@example.com", "other": "noah@example.com",
            "listing": "20L microwave — heats well, keypad needs a firm press",
            "category": "Item not as described", "summary": "Microwave keypad does not respond consistently",
            "details": "The listing says the keypad is only slightly worn, but several buttons need repeated presses. I would like the safety team to check whether the description should be updated before someone travels for a handover.",
            "priority": "high", "status": "open", "assigned": None, "days_ago": 0.4,
            "evidence": [("Photo of the keypad", "image", "/static/img/microwave-used.jpg", "Close-up shared by the reporting member.")],
            "events": [("opened", "Dispute submitted by the reporting member.", 0.4)],
        },
        {
            "code": "DSP-2040", "reporter": "josh@antiimbak.com", "other": "miguel@example.com",
            "listing": "Front-load washing machine — leaking gasket, for repair",
            "category": "Item not received", "summary": "Handover was postponed twice after the request was accepted",
            "details": "The request was accepted and I arranged a helper, but the handover has been moved twice. I would appreciate help confirming a firm schedule or closing the arrangement kindly.",
            "priority": "urgent", "status": "under_review", "assigned": "admin@antiimbak.com", "days_ago": 1.1,
            "evidence": [
                ("Handover coordination note", "note", None, "Original Saturday slot moved to Sunday, then to an unconfirmed date."),
                ("Delivery reference", "link", "/static/img/washer-gasket.jpg", "Partnered Delivery AI-6H1N4P is attached to the pending request."),
            ],
            "events": [
                ("opened", "Dispute submitted with the pending request reference.", 1.1),
                ("assigned", "Assigned to Aria Santos for casework.", 0.9),
                ("status", "Case moved to Under review while both members are contacted.", 0.7),
                ("note", "Asked the Donor to confirm a safe handover window within 48 hours.", 0.5),
            ],
        },
        {
            "code": "DSP-2039", "reporter": "lina@example.com", "other": "josh@antiimbak.com",
            "listing": "Two-seater fabric sofa — cat scratches on one arm",
            "category": "Handover arrangement problems", "summary": "Delivery address changed after the request was accepted",
            "details": "The agreed drop-off area changed to a building with no lift access. I would like the team to help us agree on a safer, clearer handover plan.",
            "priority": "medium", "status": "open", "assigned": None, "days_ago": 1.8,
            "evidence": [("Original request note", "note", None, "The request named a ground-floor drop-off in Ususan.")],
            "events": [
                ("opened", "Dispute submitted about a changed delivery plan.", 1.8),
                ("note", "Automatic safety reminder sent to both members.", 1.7),
            ],
        },
        {
            "code": "DSP-2038", "reporter": "josh@antiimbak.com", "other": "bea@example.com",
            "listing": "Acoustic guitar — beginner model, new strings",
            "category": "Delivery problems", "summary": "Delivery arrived later than the estimate",
            "details": "The guitar arrived safely, but the courier window moved by several hours. I am reporting it so the estimate can be reviewed for future deliveries.",
            "priority": "medium", "status": "resolved", "assigned": "admin@antiimbak.com",
            "resolution": "Both members confirmed the guitar arrived safely. The delivery partner note was updated and no further action is needed.",
            "days_ago": 7.2, "resolved_days_ago": 5.4,
            "evidence": [("Delivery tracking record", "note", None, "Tracking AI-3J8V5X completed successfully.")],
            "events": [
                ("opened", "Delivery timing concern submitted after a completed handover.", 7.2),
                ("assigned", "Assigned to Aria Santos.", 6.8),
                ("status", "Moved to Under review and both members contacted.", 6.2),
                ("resolved", "Delivery confirmed safe. Case resolved with a partner reminder.", 5.4),
            ],
        },
        {
            "code": "DSP-2037", "reporter": "maya@antiimbak.com", "other": "miguel@example.com",
            "listing": "Wooden blocks and shape sorter — complete set",
            "category": "Inappropriate user behavior", "summary": "Repeated off-platform contact requests",
            "details": "After a request was declined for another item, the member sent several messages asking to continue the conversation outside Anti-Imbak. I have kept everything in Messages and would like the team to review the behavior.",
            "priority": "high", "status": "closed", "assigned": "admin@antiimbak.com",
            "resolution": "Reviewed the available messages. A written warning was issued and the member was reminded of the community communication rules. The reporter was informed.",
            "days_ago": 13.4, "resolved_days_ago": 11.6,
            "evidence": [("Message log", "note", None, "Three off-platform requests were recorded after the claim was declined.")],
            "events": [
                ("opened", "Behavior concern submitted by the Donor.", 13.4),
                ("assigned", "Assigned to Aria Santos.", 13.1),
                ("status", "Moved to Under review.", 12.8),
                ("note", "Warning issued and communication policy re-sent.", 12.0),
                ("resolved", "Case resolved and closed after the warning was acknowledged.", 11.6),
            ],
        },
        {
            "code": "DSP-2036", "reporter": "noah@example.com", "other": "lina@example.com",
            "listing": "Two-seater fabric sofa — cat scratches on one arm",
            "category": "Miscommunication between users", "summary": "Conflicting handover dates",
            "details": "We each understood a different weekend for pickup. The item is safe and the request is still friendly — we just need a neutral note to confirm the arrangement.",
            "priority": "low", "status": "under_review", "assigned": "admin@antiimbak.com", "days_ago": 2.6,
            "evidence": [("Message notes", "note", None, "One member noted Saturday, the other Sunday. No safety concern.")],
            "events": [
                ("opened", "Miscommunication report submitted.", 2.6),
                ("assigned", "Assigned for a light-touch mediation.", 2.3),
                ("note", "Sent a shared message inviting both members to confirm a new date.", 1.9),
            ],
        },
    ]

    dispute_ids: dict[str, int] = {}
    for dispute in dispute_rows:
        created = stamp(now - timedelta(days=dispute["days_ago"]))
        resolved_at = stamp(now - timedelta(days=dispute["resolved_days_ago"])) if dispute.get("resolved_days_ago") else None
        cur = conn.execute(
            """INSERT INTO disputes
               (dispute_code, reporter_id, other_user_id, listing_id, category, summary, details,
                priority, status, assigned_admin_id, resolution, created_at, updated_at, resolved_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                dispute["code"], user_ids[dispute["reporter"]], user_ids.get(dispute["other"]),
                listing_ids.get(dispute["listing"]), dispute["category"], dispute["summary"],
                dispute["details"], dispute["priority"], dispute["status"],
                user_ids.get(dispute["assigned"]) if dispute["assigned"] else None,
                dispute.get("resolution"), created, resolved_at or created, resolved_at,
            ),
        )
        dispute_id = cur.lastrowid
        dispute_ids[dispute["code"]] = dispute_id
        for title, kind, file_url, note in dispute["evidence"]:
            conn.execute(
                """INSERT INTO dispute_evidence (dispute_id, title, kind, file_url, note, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (dispute_id, title, kind, file_url, note, created),
            )
        for event_type, note, days_ago in dispute["events"]:
            conn.execute(
                """INSERT INTO dispute_events (dispute_id, actor_id, event_type, note, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    dispute_id,
                    user_ids["admin@antiimbak.com"] if event_type in {"assigned", "status", "note", "resolved"} else user_ids[dispute["reporter"]],
                    event_type, note, stamp(now - timedelta(days=days_ago)),
                ),
            )

    support_rows = [
        {
            "code": "SUP-3101", "user": "josh@antiimbak.com", "category": "Claim request concerns",
            "subject": "How do I confirm I received my delivery?",
            "message": "My guitar delivery is complete but I want to make sure the handover is recorded properly on my account. Which button should I use?",
            "priority": "high", "status": "in_progress", "assigned": "admin@antiimbak.com", "days_ago": 0.7,
            "messages": [
                ("Member", 0, "My guitar delivery is complete but I want to make sure the handover is recorded properly on my account. Which button should I use?", 0.7),
                ("Support team", 1, "Open My Requests, find the completed guitar claim and choose View details. The delivery tracker shows Successfully Delivered and the request is already complete. Nothing else is needed.", 0.4),
            ],
        },
        {
            "code": "SUP-3102", "user": "bea@example.com", "category": "Account problems",
            "subject": "My verification badge disappeared",
            "message": "I noticed my profile no longer shows the verified badge. Could someone check whether my verification is still active?",
            "priority": "medium", "status": "open", "assigned": None, "days_ago": 1.2,
            "messages": [("Member", 0, "I noticed my profile no longer shows the verified badge. Could someone check whether my verification is still active?", 1.2)],
        },
        {
            "code": "SUP-3103", "user": "lina@example.com", "category": "Donation listing problems",
            "subject": "Recipient asked me to change the handover point",
            "message": "A Recipient asked me to move the handover to a residential address. I want to keep it public and safe. Is there a standard reply I can use?",
            "priority": "high", "status": "open", "assigned": None, "days_ago": 0.9,
            "messages": [("Member", 0, "A Recipient asked me to move the handover to a residential address. I want to keep it public and safe. Is there a standard reply I can use?", 0.9)],
        },
        {
            "code": "SUP-3104", "user": "miguel@example.com", "category": "Technical issues",
            "subject": "Photo preview did not load on my phone",
            "message": "When I tried to add a photo from my phone, the preview stayed blank. I was able to upload it on my laptop, but wanted to report it.",
            "priority": "medium", "status": "resolved", "assigned": "admin@antiimbak.com",
            "resolution": "Guided the member through a smaller upload and recorded the phone preview issue for the next build.",
            "days_ago": 4.6, "resolved_days_ago": 3.8,
            "messages": [
                ("Member", 0, "When I tried to add a photo from my phone, the preview stayed blank. I was able to upload it on my laptop, but wanted to report it.", 4.6),
                ("Support team", 1, "Thanks for flagging it. A smaller image should work more reliably. We recorded the phone preview issue for the next build.", 4.1),
                ("Member", 0, "That worked. Thank you!", 3.9),
            ],
        },
        {
            "code": "SUP-3105", "user": "noah@example.com", "category": "Suggestions",
            "subject": "Add a condition checklist before confirming",
            "message": "It would be helpful to have a short checklist before a Donor accepts a request, like confirming the item is clean and all parts are included.",
            "priority": "low", "status": "closed", "assigned": "admin@antiimbak.com",
            "resolution": "Added to the product suggestion board for the next release.",
            "days_ago": 16.2, "resolved_days_ago": 14.8,
            "messages": [
                ("Member", 0, "It would be helpful to have a short checklist before a Donor accepts a request, like confirming the item is clean and all parts are included.", 16.2),
                ("Support team", 1, "This is a thoughtful suggestion. We have added it to the product board for the next release.", 15.1),
            ],
        },
        {
            "code": "SUP-3106", "user": "josh@antiimbak.com", "category": "Delivery concerns",
            "subject": "Can the delivery partner be changed?",
            "message": "My washing machine request is still pending, but the item is bulky. Can the Partnered Delivery use a van rather than a motorcycle?",
            "priority": "urgent", "status": "open", "assigned": None, "days_ago": 0.2,
            "messages": [("Member", 0, "My washing machine request is still pending, but the item is bulky. Can the Partnered Delivery use a van rather than a motorcycle?", 0.2)],
        },
        {
            "code": "SUP-3107", "user": "maya@antiimbak.com", "category": "General inquiries",
            "subject": "Can I list a repaired appliance?",
            "message": "I have a small appliance I repaired myself. Is it allowed to list it as a donation if I describe the repair clearly?",
            "priority": "low", "status": "in_progress", "assigned": "admin@antiimbak.com", "days_ago": 2.1,
            "messages": [
                ("Member", 0, "I have a small appliance I repaired myself. Is it allowed to list it as a donation if I describe the repair clearly?", 2.1),
                ("Support team", 1, "Yes — repaired items are welcome when the repair and any remaining faults are described honestly. Please include safety notes and a clear photo in the listing.", 1.6),
            ],
        },
    ]
    support_ids: dict[str, int] = {}
    for concern in support_rows:
        created = stamp(now - timedelta(days=concern["days_ago"]))
        resolved_at = stamp(now - timedelta(days=concern["resolved_days_ago"])) if concern.get("resolved_days_ago") else None
        cur = conn.execute(
            """INSERT INTO support_concerns
               (ticket_code, user_id, category, subject, message, priority, status,
                assigned_admin_id, resolution, created_at, updated_at, resolved_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                concern["code"], user_ids[concern["user"]], concern["category"], concern["subject"],
                concern["message"], concern["priority"], concern["status"],
                user_ids.get(concern["assigned"]) if concern["assigned"] else None,
                concern.get("resolution"), created, resolved_at or stamp(now - timedelta(days=concern.get("resolved_days_ago", concern["days_ago"]))), resolved_at,
            ),
        )
        concern_id = cur.lastrowid
        support_ids[concern["code"]] = concern_id
        for sender_label, is_admin, body, days_ago in concern["messages"]:
            conn.execute(
                """INSERT INTO support_messages (concern_id, sender_id, sender_label, body, is_admin, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    concern_id,
                    user_ids["admin@antiimbak.com"] if is_admin else user_ids[concern["user"]],
                    sender_label, body, is_admin, stamp(now - timedelta(days=days_ago)),
                ),
            )

    conn.executemany(
        "INSERT INTO safety_tips (text, sort_order) VALUES (?, ?)",
        [
            ("Meet in a public, well-lit place whenever possible — a mall lobby, barangay hall or café.", 1),
            ("Bring a friend or family member, especially for evening handovers or bulky items.", 2),
            ("Tell someone you trust where you are going and who you are meeting.", 3),
            ("Keep conversations inside Anti-Imbak until a request is accepted, then share only what is needed to coordinate.", 4),
            ("Never share passwords, one-time codes or financial details with another member.", 5),
            ("Inspect items before taking them, and check that the handover matches the listing and condition.", 6),
            ("Report suspicious accounts, unsafe requests or misleading listings right away.", 7),
        ],
    )

    notification_rows = [
        ("maya@antiimbak.com", "claim_request", "New claim request", "Bea wants to give your Acer laptop a new purpose.", "/dashboard/claims", 0, 0.7),
        ("maya@antiimbak.com", "claim_request", "New claim request", "Lina has requested your clothing bundle for a women's shelter.", "/dashboard/claims", 0, 1.3),
        ("maya@antiimbak.com", "message", "New message from Bea", "Got it. I submitted a request. Thank you for answering everything.", "/dashboard/messages?conversation=" + str(conversation_ids[("maya@antiimbak.com", "bea@example.com")]), 0, 0.2),
        ("maya@antiimbak.com", "listing_update", "Your donation is live", "Running shoes — US 8, sole starting to separate is now visible to the community.", "/listings/" + str(listing_ids["Running shoes — US 8, sole starting to separate"]), 1, 0.2),
        ("noah@example.com", "featured_expired", "Featured listing ended", "The promotion for your microwave has ended. Your listing is still live and free.", "/dashboard/donations", 1, 26),
        ("noah@example.com", "claim_request", "New claim request", "Bea has requested your microwave for a shared student dorm.", "/dashboard/claims", 0, 0.6),
        ("josh@antiimbak.com", "claim_accepted", "Request accepted", "Noah accepted your request for the dumbbells. Arrange the Self Pickup through Messages.", "/dashboard/claims/mine", 0, 1.8),
        ("josh@antiimbak.com", "delivery_update", "Successfully Delivered", "Your guitar delivery is complete. We hope it brings you many songs.", "/dashboard/claims/mine", 1, 18),
        ("josh@antiimbak.com", "claim_rejected", "Claim update", "The sofa has found another home. Plenty more useful items are waiting.", "/dashboard/claims/mine", 1, 3.2),
        ("josh@antiimbak.com", "message", "New message from Miguel", "Please send it. We chose Partnered Delivery because a jeepney is not realistic for this.", "/dashboard/messages?conversation=" + str(conversation_ids[("miguel@example.com", "josh@antiimbak.com")]), 0, 1.2),
        ("admin@antiimbak.com", "announcement", "Two reports await review", "The trust and safety queue has new community reports.", "/admin/reports", 0, 0.3),
        ("admin@antiimbak.com", "advertisement", "New advertising inquiry", "GreenHaul Junk Removal asked about the Sponsored Business Card.", "/admin/content", 0, 1.1),
        ("bea@example.com", "claim_request", "Request submitted", "Your request for the Acer laptop is with Maya. We'll let you know when there is an update.", "/dashboard/claims/mine", 0, 0.8),
        ("miguel@example.com", "claim_request", "Request submitted", "Your request for the wooden toys is being reviewed.", "/dashboard/claims/mine", 0, 0.4),
        ("lina@example.com", "claim_request", "Request submitted", "Your request for the clothing bundle is being reviewed by the Donor.", "/dashboard/claims/mine", 0, 1.3),
    ]
    for email, typ, title, message, link, is_read, days_ago in notification_rows:
        conn.execute(
            """INSERT INTO notifications (user_id, type, title, message, link, is_read, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_ids[email], typ, title, message, link, is_read, stamp(now - timedelta(days=days_ago))),
        )

    admin_id = user_ids["admin@antiimbak.com"]
    conn.execute(
        """INSERT INTO admin_logs (admin_id, action, target_type, target_id, details, created_at)
           VALUES (?, 'Resolved report', 'report', ?, 'Gallery reviewed and cleaned up.', ?)""",
        (admin_id, resolved_report.lastrowid, stamp(now - timedelta(days=5))),
    )
    conn.execute(
        """INSERT INTO admin_logs (admin_id, action, target_type, target_id, details, created_at)
           VALUES (?, 'Reviewed listing', 'listing', ?, 'Verified item photos and condition notes.', ?)""",
        (admin_id, listing_ids["Acer Aspire 5 laptop — i5, 8GB RAM, 256GB SSD"], stamp(now - timedelta(days=1))),
    )
    conn.execute(
        """INSERT INTO admin_logs (admin_id, action, target_type, target_id, details, created_at)
           VALUES (?, 'Resolved dispute', 'dispute', ?, 'Delivery confirmed safe; closed with a courier reminder.', ?)""",
        (admin_id, dispute_ids["DSP-2038"], stamp(now - timedelta(days=5.4))),
    )
    conn.execute(
        """INSERT INTO admin_logs (admin_id, action, target_type, target_id, details, created_at)
           VALUES (?, 'Replied to user concern', 'support_concern', ?, 'Explained how to review a completed delivery.', ?)""",
        (admin_id, support_ids["SUP-3101"], stamp(now - timedelta(days=0.4))),
    )
    conn.execute(
        """INSERT INTO admin_logs (admin_id, action, target_type, target_id, details, created_at)
           VALUES (?, 'Featured listing approved', 'listing', ?, 'Granted a 14-day editorial feature with no charge.', ?)""",
        (admin_id, listing_ids["Mountain bike — 26er, brakes need adjustment"], stamp(now - timedelta(days=1.8))),
    )
    conn.execute(
        """INSERT INTO admin_logs (admin_id, action, target_type, target_id, details, created_at)
           VALUES (?, 'Updated advertisement', 'advertisement', 2, 'Refreshed the MoveEasy truck rental creative.', ?)""",
        (admin_id, stamp(now - timedelta(hours=9))),
    )
    conn.execute(
        """INSERT INTO admin_logs (admin_id, action, target_type, target_id, details, created_at)
           VALUES (?, 'Reviewed dispute', 'dispute', ?, 'Requested a firm handover window from the Donor.', ?)""",
        (admin_id, dispute_ids["DSP-2040"], stamp(now - timedelta(hours=12))),
    )

    _ = (open_report_1, open_report_2, guitar_claim)


def reset_database() -> None:
    """Recreate the database from the canonical schema and seed data."""
    for suffix in ("", "-wal", "-shm"):
        path = Path(str(DATABASE_PATH) + suffix)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    init_db(force=True)


if __name__ == "__main__":
    reset_database()
    print(f"Rebuilt {DATABASE_PATH} with sample marketplace data.")
