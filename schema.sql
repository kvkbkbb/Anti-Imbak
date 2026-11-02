PRAGMA foreign_keys = ON;

-- Identity and access -------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    email           TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password_hash   TEXT    NOT NULL,
    role            TEXT    NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    status          TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
    email_verified  INTEGER NOT NULL DEFAULT 0 CHECK (email_verified IN (0, 1)),
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login      TEXT
);

CREATE TABLE IF NOT EXISTS profiles (
    user_id         INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    avatar_url      TEXT,
    contact_number  TEXT,
    location        TEXT,
    city            TEXT,
    latitude        REAL,
    longitude       REAL,
    bio             TEXT,
    verified        INTEGER NOT NULL DEFAULT 0 CHECK (verified IN (0, 1)),
    member_since    TEXT
);

CREATE TABLE IF NOT EXISTS password_resets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      TEXT    NOT NULL UNIQUE,
    expires_at      TEXT    NOT NULL,
    used            INTEGER NOT NULL DEFAULT 0 CHECK (used IN (0, 1)),
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Marketplace ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,
    slug            TEXT    NOT NULL UNIQUE,
    icon            TEXT    NOT NULL,
    description     TEXT,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    active          INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS listings (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    donor_id            INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id         INTEGER NOT NULL REFERENCES categories(id),
    title               TEXT    NOT NULL,
    description         TEXT    NOT NULL,
    condition           TEXT    NOT NULL CHECK (condition IN ('Like New', 'Good', 'Fair', 'For Repair', 'Nonfunctional')),
    item_size           TEXT    NOT NULL DEFAULT 'medium' CHECK (item_size IN ('small', 'medium', 'large')),
    city                TEXT    NOT NULL,
    area                TEXT    NOT NULL,
    latitude            REAL    NOT NULL,
    longitude           REAL    NOT NULL,
    status              TEXT    NOT NULL DEFAULT 'available'
                                CHECK (status IN ('available', 'reserved', 'claimed', 'unavailable', 'removed')),
    is_featured         INTEGER NOT NULL DEFAULT 0 CHECK (is_featured IN (0, 1)),
    featured_until      TEXT,
    views               INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS listing_images (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id      INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    image_url       TEXT    NOT NULL,
    alt_text        TEXT,
    sort_order      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS claims (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id      INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    claimant_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message         TEXT    NOT NULL,
    receive_method  TEXT    NOT NULL DEFAULT 'delivery' CHECK (receive_method IN ('pickup', 'delivery')),
    delivery_address TEXT,
    status          TEXT    NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'accepted', 'rejected', 'completed', 'cancelled')),
    donor_note      TEXT,
    handover_confirmed INTEGER NOT NULL DEFAULT 0 CHECK (handover_confirmed IN (0, 1)),
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (listing_id, claimant_id)
);

CREATE TABLE IF NOT EXISTS saved_listings (
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    listing_id      INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, listing_id)
);

CREATE TABLE IF NOT EXISTS notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type            TEXT    NOT NULL,
    title           TEXT    NOT NULL,
    message         TEXT    NOT NULL,
    link            TEXT,
    is_read         INTEGER NOT NULL DEFAULT 0 CHECK (is_read IN (0, 1)),
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id      INTEGER REFERENCES listings(id) ON DELETE SET NULL,
    claim_id        INTEGER REFERENCES claims(id) ON DELETE SET NULL,
    donor_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipient_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (listing_id, donor_id, recipient_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    sender_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body            TEXT    NOT NULL,
    attachment_url  TEXT,
    read_at         TEXT,
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Trust and safety ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS reports (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    listing_id      INTEGER REFERENCES listings(id) ON DELETE CASCADE,
    reported_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reason          TEXT    NOT NULL,
    details         TEXT,
    status          TEXT    NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved', 'dismissed')),
    admin_note      TEXT,
    resolved_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at     TEXT
);

CREATE TABLE IF NOT EXISTS safety_tips (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    text            TEXT    NOT NULL,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    active          INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

-- Disputes and user support --------------------------------------------------
CREATE TABLE IF NOT EXISTS disputes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    dispute_code    TEXT    NOT NULL UNIQUE,
    reporter_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    other_user_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    listing_id      INTEGER REFERENCES listings(id) ON DELETE SET NULL,
    category        TEXT    NOT NULL,
    summary         TEXT    NOT NULL,
    details         TEXT,
    priority        TEXT    NOT NULL DEFAULT 'medium'
                            CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    status          TEXT    NOT NULL DEFAULT 'open'
                            CHECK (status IN ('open', 'under_review', 'resolved', 'closed')),
    assigned_admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    resolution      TEXT,
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at     TEXT
);

CREATE TABLE IF NOT EXISTS dispute_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    dispute_id      INTEGER NOT NULL REFERENCES disputes(id) ON DELETE CASCADE,
    actor_id        INTEGER REFERENCES users(id) ON DELETE SET NULL,
    event_type      TEXT    NOT NULL,
    note            TEXT,
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dispute_evidence (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    dispute_id      INTEGER NOT NULL REFERENCES disputes(id) ON DELETE CASCADE,
    title           TEXT    NOT NULL,
    kind            TEXT    NOT NULL DEFAULT 'image',
    file_url        TEXT,
    note            TEXT,
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS support_concerns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_code     TEXT    NOT NULL UNIQUE,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category        TEXT    NOT NULL,
    subject         TEXT    NOT NULL,
    message         TEXT    NOT NULL,
    priority        TEXT    NOT NULL DEFAULT 'medium'
                            CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    status          TEXT    NOT NULL DEFAULT 'open'
                            CHECK (status IN ('open', 'in_progress', 'resolved', 'closed')),
    assigned_admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    resolution      TEXT,
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at     TEXT
);

CREATE TABLE IF NOT EXISTS support_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    concern_id      INTEGER NOT NULL REFERENCES support_concerns(id) ON DELETE CASCADE,
    sender_id       INTEGER REFERENCES users(id) ON DELETE SET NULL,
    sender_label    TEXT    NOT NULL DEFAULT 'Member',
    body            TEXT    NOT NULL,
    is_admin        INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0, 1)),
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Promotions, delivery and revenue -----------------------------------------
CREATE TABLE IF NOT EXISTS featured_listings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id      INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    donor_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    package         TEXT    NOT NULL CHECK (package IN ('featured', 'premium')),
    amount          REAL    NOT NULL DEFAULT 0,
    starts_at       TEXT    NOT NULL,
    ends_at         TEXT    NOT NULL,
    transaction_id  INTEGER,
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS delivery_partners (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    slug            TEXT    NOT NULL UNIQUE,
    service_type    TEXT    NOT NULL,
    eta             TEXT,
    description     TEXT,
    active          INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS delivery_requests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id        INTEGER NOT NULL UNIQUE REFERENCES claims(id) ON DELETE CASCADE,
    listing_id      INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    requester_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    partner_id      INTEGER REFERENCES delivery_partners(id) ON DELETE SET NULL,
    pickup_address  TEXT    NOT NULL,
    dropoff_address TEXT    NOT NULL,
    distance_km     REAL    NOT NULL,
    fee             REAL    NOT NULL CHECK (fee >= 50 AND fee <= 150),
    status          TEXT    NOT NULL DEFAULT 'request_accepted'
                            CHECK (status IN ('request_accepted', 'awaiting_dispatch', 'in_progress', 'arriving_soon', 'delivered', 'cancelled')),
    tracking_code   TEXT    NOT NULL UNIQUE,
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,
    type            TEXT    NOT NULL CHECK (type IN ('featured', 'delivery', 'advertisement')),
    reference_type  TEXT,
    reference_id    INTEGER,
    amount          REAL    NOT NULL,
    platform_fee    REAL    NOT NULL DEFAULT 0,
    provider_payout REAL    NOT NULL DEFAULT 0,
    payment_method  TEXT    NOT NULL DEFAULT 'Recorded',
    description     TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'completed' CHECK (status IN ('completed', 'refunded', 'failed')),
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Advertising ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ad_packages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    placement       TEXT    NOT NULL,
    price           REAL    NOT NULL,
    duration_days   INTEGER NOT NULL,
    description     TEXT,
    active          INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS advertisements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    advertiser_name TEXT    NOT NULL,
    business_type   TEXT    NOT NULL,
    title           TEXT    NOT NULL,
    body            TEXT,
    cta_label       TEXT    NOT NULL DEFAULT 'Learn more',
    cta_url         TEXT,
    image_url       TEXT,
    placement       TEXT    NOT NULL CHECK (placement IN ('home_banner', 'browse_sidebar', 'category')),
    category_id     INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    package_id      INTEGER REFERENCES ad_packages(id) ON DELETE SET NULL,
    status          TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'expired')),
    starts_at       TEXT    NOT NULL,
    ends_at         TEXT    NOT NULL,
    impressions     INTEGER NOT NULL DEFAULT 0,
    clicks          INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ad_inquiries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    email           TEXT    NOT NULL,
    business_name   TEXT    NOT NULL,
    business_type   TEXT    NOT NULL,
    package_id      INTEGER REFERENCES ad_packages(id) ON DELETE SET NULL,
    message         TEXT,
    status          TEXT    NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'contacted', 'closed')),
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action          TEXT    NOT NULL,
    target_type     TEXT,
    target_id       INTEGER,
    details         TEXT,
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status);
CREATE INDEX IF NOT EXISTS idx_listings_category ON listings(category_id);
CREATE INDEX IF NOT EXISTS idx_listings_created ON listings(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_listings_featured ON listings(is_featured, featured_until);
CREATE INDEX IF NOT EXISTS idx_claims_listing ON claims(listing_id, status);
CREATE INDEX IF NOT EXISTS idx_claims_claimant ON claims(claimant_id, status);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_donor ON conversations(donor_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_recipient ON conversations(recipient_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_unread ON messages(conversation_id, read_at, sender_id);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_disputes_status ON disputes(status, priority, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_dispute_events ON dispute_events(dispute_id, created_at);
CREATE INDEX IF NOT EXISTS idx_support_status ON support_concerns(status, priority, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_support_messages ON support_messages(concern_id, created_at);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ads_placement ON advertisements(placement, status);
