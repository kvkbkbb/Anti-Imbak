# Anti-Imbak

**Giving Items a Second Purpose.**

Anti-Imbak is a donation-only community marketplace. People give away items they no longer need, and people who need them can browse, save, claim, and arrange a handover. Items are never sold: there is intentionally no price field anywhere in the product.

This is a complete, self-contained community marketplace built with Flask, SQLite, Jinja templates, and vanilla JavaScript. It runs locally with no Node.js build step, no external database, and no third-party services.

---

## Quick start

**Requirements:** Python 3.11+ (tested on Python 3.14) and pip.

```powershell
# From the Anti-Imbak folder
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Optional: rebuild the sample database from scratch
python db.py

# Start the app
python app.py
```

Open **http://127.0.0.1:5000**.

The SQLite database is created automatically at `instance/antiimbak.db` the first time the app starts. The sample accounts below are seeded automatically.

### Environment variables

| Variable | Purpose |
| --- | --- |
| `ANTI_IMBAK_SECRET` | Overrides the generated Flask secret. Otherwise `instance/secret.key` is created on first run. |
| `ANTI_IMBAK_COOKIE_SECURE` | Set to `1` to mark session cookies `Secure` behind HTTPS. |
| `PORT` | Local port used by `python app.py` (default `5000`). |

---

## Sample accounts

| View | Sample person | Email | Password | What to explore |
| --- | --- | --- | --- | --- |
| Administrator | Aria Santos | `admin@antiimbak.com` | `Aria123!` | Operations overview, member directory, listing moderation, disputes, user concerns, activity logs, revenue, and content management |
| Donor | Maya Reyes | `maya@antiimbak.com` | `Maya123!` | My Listings, listing performance, incoming claim requests, messages, notifications, and account settings |
| Recipient | Josh Mendoza | `josh@antiimbak.com` | `Josh123!` | My Requests, saved items, messages, notifications, delivery tracking, and account settings |

The login page also includes one-click sample account buttons for these three people.

### View as

Every page carries a **View as** bar with four perspectives: **Public Marketplace**, **Donor**, **Recipient**, and **Administrator**. Switching changes the session perspective and opens that role's starting page. **Reset sample data** restores the original listings, claims, disputes, support threads, users, notifications, and revenue ledger, then returns to the public homepage.

When a guest tries a member action such as claiming an item, saving a find, or donating, Anti-Imbak shows a friendly account-access prompt. It explains the account gate and offers one-click continuation with the matching sample account, preserving the intended listing or page. The public marketplace itself never requires an account.

**All seed data is synthetic.** Names, listings, claims, messages, dates, fees, and revenue entries exist only to make the workflow explorable. No real people, payments, couriers, or transactions are represented.

---

## What works

### Public experience

- Landing page with live, database-derived discovery and community metrics
- Hero search and location shortcut, popular categories, featured and recent donations, and useful items nearby
- Marketplace browsing with search, category, condition, city, and sort filters
- Listing detail pages with gallery, safety guidance, Donor profiles, save, claim, and report actions
- Donation-only claim flow with **Partnered Delivery** selected by default and **Self Pickup** available as an alternative
- Distinct visual treatments for featured, recent, regular, unavailable, claimed, and repair listings
- “How it works”, About, Safety & Trust, Advertise, Privacy, and Terms pages
- Registration, login, logout, forgot password, and reset password
- Sponsored advertisement landing pages with locally tracked impressions and clicks

### Donor workspace

- **My Listings** with live counts, status filters, views, saves, requests, and management actions
- Create, edit, publish, pause, boost, mark unavailable, and remove donations
- Photo uploads (JPG/PNG/WebP) or bundled sample-photo selection
- **Claim Requests** with Recipient profiles, the request message, handover method, and accept/decline actions
- **Messages** to answer condition questions and agree the handover in one place
- **Notifications** for new requests, messages, and delivery updates
- **Account Settings** for profile details, password, and notification preferences

### Recipient workspace

- **My Requests** with status, Donor details, handover method, delivery tracking, and message shortcuts
- **Saved Items** kept in the workspace for later
- **Messages** to ask about condition, measurements, photos, and handover plans before or after claiming
- Claim submission with a personal message and automatic Partnered Delivery quote
- Request tracking from review through acceptance and delivery
- **Notifications** and **Account Settings**

### Messaging

- Messenger-style split view with a conversation list and a dedicated chat pane
- Names, avatars, listing context, previews, timestamps, unread badges, and instant search
- Sent and received bubbles, sender labels, time-ago stamps, and independent scrolling
- Composer with text, image attachments, Enter-to-send, and an option to reuse the listing photo
- Mobile list/chat switching with a back control, so the inbox stays usable on small screens
- Entry points from the main navigation, member navigation, listing details, claim pages, and notifications

### Partnered Delivery

- Selected automatically when a Recipient sends a claim
- Courier partner assigned automatically based on the item's size
- One inclusive fee from **₱50 to ₱150**, varying by item size and distance
- Fee rounded to the nearest ₱5 and passed in full to the delivery partner, with no extra charge from the platform
- Visible before the claim is submitted and recorded on the claim detail
- Progress shown as **Request Accepted → Awaiting Dispatch → Delivery in Progress → Arriving Soon → Successfully Delivered**
- Recipient may instead choose **Self Pickup** at claim time; meeting details are arranged in Messages, never through a pickup-instructions form

### Admin console

- Community overview with live counts, activity chart, category distribution, open reports, claims waiting, active disputes, user concerns, revenue, featured listings, and audit trail
- User directory with Donor/Recipient filters, member detail views, and account actions
- Listing moderation, status changes, and removal
- Dedicated **Disputes Management** with priority and status queues, case detail pages, evidence, parties, notes, resolutions, and full case history
- Dedicated **User Concerns & Support** inbox with message threads, replies, status/assignment controls, and escalation guidance
- Paginated **Activity logs** with target and text filters
- Report queue with resolution notes and audit logging
- Revenue ledger with CSV export
- Advertisement creation, live inventory, status control, packages, categories, safety tips, announcements, and advertiser inquiries
- Member workspace and public site shortcuts

### Cross-cutting behaviour

- CSRF protection on every state-changing POST
- Password hashing with Werkzeug
- Role-based decorators, ownership checks, and server-side validation
- Content Security Policy with **no inline scripts**; all JavaScript lives in `static/js/`
- Security headers, upload type/size limits, and soft removal for listings
- Responsive layouts for desktop, tablet, and mobile
- Independent scrolling for the member/admin workspace and navigation on tall screens
- Local web fonts and no external asset requests

---

## Brand and design

The wordmark deliberately pairs two typefaces:

- **Anti** — Chakra Petch italic, angular and cyan
- **Imbak** — Outfit, rounded, white/silver

Full, compact, icon-only, light-background, and dark-background logo variations are defined in the templates and styles. The visual language is futuristic and editorial rather than game-like. All fonts are bundled in `static/fonts/`.

The interface preserves one shared design system while giving each component family a clear purpose: primary, secondary, positive, warning, destructive, and informational buttons; featured, recent, regular, unavailable, claimed, and repair listing treatments; and distinct member, admin, and messaging surfaces.

---

## Project structure

```text
Anti-Imbak/
|-- app.py                  # App factory, CSRF, filters, security headers, errors
|-- db.py                   # Schema bootstrap and sample marketplace seed
|-- schema.sql              # Canonical SQLite schema
|-- services.py             # Shared helpers, auth utilities, delivery quotes
|-- requirements.txt
|-- instance/
|   `-- antiimbak.db        # Created at runtime
|-- routes/
|   |-- public.py           # Landing, marketplace, listings, static content
|   |-- auth.py             # Register, login, logout, password reset
|   |-- dashboard.py        # Member listings, claims, messaging, settings
|   |-- admin.py            # Moderation, users, disputes, support, revenue, content
|   `-- api.py              # Delivery quote endpoint
|-- templates/
|   |-- base.html           # Public shell and View as bar
|   |-- dashboard/          # Donor/Recipient workspace shell and pages
|   |-- admin/              # Admin shell, disputes, support and activity pages
|   `-- ...
`-- static/
    |-- css/
    |   |-- styles.css      # Foundation, tokens, shared components
    |   |-- pages.css       # Public page modules
    |   |-- dashboard.css   # Member dashboard modules
    |   |-- admin.css       # Admin console modules
    |   `-- responsive.css  # Tablet and mobile overrides (loaded last)
    |-- js/
    |   |-- app.js          # Menus, modals, toggles, previews, messaging helpers
    |   `-- advertise.js    # Advertising form helpers
    |-- fonts/
    |-- img/
    `-- uploads/            # Member uploads (empty in a fresh install)
```

---

## Prototype scope

This project is a locally runnable marketplace prototype, not a production service. The distinction matters:

**Fully implemented locally**

- Accounts, sessions, password resets, claims, listings, saved items, notifications, reports, moderation, delivery records, advertisements, categories, safety tips, announcements, and admin actions
- Every count, chart, ledger row, and metric is queried from SQLite
- Uploaded images are stored locally and served by Flask

**Deliberately simulated**

- **Payments** — Featured boosts, advertising packages, and delivery fees are recorded locally. No payment gateway is contacted and no money moves. Boost and ad receipts are sample transactions.
- **Couriers** — Delivery quotes, tracking steps, and statuses are simulated locally. No courier API, live GPS, or real booking exists.
- **Email and SMS** — Notifications remain in-app. Password reset links are shown on screen instead of being emailed because no mail provider is configured.
- **Advertising delivery** — Ad impressions and clicks are counted in the local database; there is no external ad network.
- **Seed content** — Listings, conversations, histories, and revenue entries are synthetic sample data.

---

## Data reset and maintenance

Use **Reset sample data** in the View as bar to restore the original sample state. It reseeds users, listings, claims, notifications, disputes, dispute evidence and events, support concerns and messages, admin logs, and revenue, keeps the current browser signed out, and returns to the public homepage.

To rebuild the database from the command line instead:

```powershell
python db.py
```

Both routes **recreate** `instance/antiimbak.db` and reseed the sample accounts and content. Any accounts, listings, claims, messages, or uploads created during testing will be lost. Uploaded files in `static/uploads/` are not removed by this command.

The app also expires stale password-reset tokens and handles listing/report state transitions when requests are made.

---

## Security notes

- Every state-changing form includes a CSRF token validated server-side.
- Passwords are hashed with Werkzeug; plaintext passwords are never stored.
- Admin routes require the `admin` role; member resources check ownership.
- CSP restricts scripts to same-origin files and frames to the same origin. There are no inline `<script>` blocks.
- SESSION cookies are HTTP-only and SameSite=Lax. Set `ANTI_IMBAK_COOKIE_SECURE=1` in an HTTPS deployment.
- Uploads accept only JPG, PNG, and WebP, with per-file and total-request limits.
- Listings are soft-removed so related claims, reports, and audit records remain intact.

For a production deployment you would additionally need a real database server, HTTPS, a mail provider, a payment gateway, courier integration, object storage, rate limiting, and a background job runner.

---

## Verification

The application has been exercised end to end with Flask’s test client across registration, authentication, password reset, profile updates, listing creation and editing, boosts, delivery-default and pickup claims, claim state transitions, handover confirmation, delivery tracking, saved items, reports, advertisements, packages, categories, safety tips, announcements, inquiries, admin moderation, dispute casework, support replies, messaging, activity filtering, role-view switching, and sample-data reset.

Responsive QA covered public pages, member workspaces, messaging, claim detail, and the admin console at desktop, tablet, and mobile widths. Every figure shown in the UI comes from the live sample database.

---

## License and attribution

This is a locally runnable prototype. Brand names, copy, and seed content were created for Anti-Imbak. Bundled fonts are Chakra Petch, Outfit, and Manrope; product photography uses the bundled sample assets in `static/img/`.
