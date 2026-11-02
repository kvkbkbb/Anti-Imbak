"""Build the static GitHub Pages preview of Anti-Imbak.

GitHub Pages only serves static files, while Anti-Imbak is a Flask application.
This script renders the public, guest-facing experience from the seeded database
into ``docs/`` so the marketplace can be browsed on GitHub Pages. Account and
write actions stay in the Flask app; the exported pages show a short notice when
someone tries to use them.

Usage (from the repository root):

    python db.py                 # optional: rebuild the sample database
    python tools/build_pages.py

The generated ``docs/`` folder is committed and published from the ``main``
branch with GitHub Pages.
"""
from __future__ import annotations

import html
import re
import shutil
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
STATIC_SRC = ROOT / "static"
SOURCE_DB = ROOT / "instance" / "antiimbak.db"

REPO_URL = "https://github.com/payonilanz/Anti-Imbak"
PAGES_URL = "https://payonilanz.github.io/Anti-Imbak"

# Content routes that map one-to-one onto a static file.
STATIC_PAGES = {
    "/": "index.html",
    "/browse": "browse.html",
    "/how-it-works": "how-it-works.html",
    "/about": "about.html",
    "/safety": "safety.html",
    "/advertise": "advertise.html",
    "/privacy": "privacy.html",
    "/terms": "terms.html",
    "/auth/login": "login.html",
    "/auth/register": "register.html",
    "/auth/forgot-password": "forgot-password.html",
    "/demo/access": "access.html",
}

PREVIEW_CSS = """\
/* Static GitHub Pages preview chrome. */
.static-preview-bar {
  position: relative;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 0.45rem 0.7rem;
  padding: 0.5rem 1rem;
  border-bottom: 1px solid rgba(57, 231, 244, 0.22);
  background: #071226;
  color: #c5d2e9;
  font-family: "Manrope", "Segoe UI", system-ui, sans-serif;
  font-size: 0.74rem;
  line-height: 1.35;
  text-align: center;
}

.static-preview-bar strong {
  color: #8ff7fc;
  font-weight: 750;
}

.static-preview-bar a {
  color: #8ff7fc;
  font-weight: 700;
  text-decoration: none;
  white-space: nowrap;
}

.static-preview-bar a:hover,
.static-preview-bar a:focus-visible {
  text-decoration: underline;
}

.static-preview-links {
  display: inline-flex;
  align-items: center;
  gap: 0.1rem;
  padding: 0.14rem;
  border: 1px solid rgba(57, 231, 244, 0.22);
  border-radius: 999px;
  background: rgba(57, 231, 244, 0.05);
}

.static-preview-links a {
  padding: 0.16rem 0.5rem;
  border-radius: 999px;
  color: #9fb4d4;
  font-size: 0.66rem;
  font-weight: 750;
  text-decoration: none;
}

.static-preview-links a:hover,
.static-preview-links a:focus-visible {
  background: rgba(57, 231, 244, 0.1);
  color: #d9fbfe;
  text-decoration: none;
}

.static-preview-links a.is-current {
  background: rgba(57, 231, 244, 0.16);
  color: #8ff7fc;
}

.static-preview-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.18rem 0.5rem;
  border: 1px solid rgba(57, 231, 244, 0.35);
  border-radius: 999px;
  background: rgba(57, 231, 244, 0.1);
  color: #8ff7fc;
  font-size: 0.6rem;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  white-space: nowrap;
}

.static-preview-toast {
  position: fixed;
  left: 50%;
  bottom: 1.4rem;
  z-index: 400;
  width: min(32rem, calc(100vw - 2rem));
  padding: 0.85rem 1rem;
  border: 1px solid rgba(57, 231, 244, 0.35);
  border-radius: 14px;
  background: #0a1730;
  box-shadow: 0 22px 60px -22px rgba(0, 0, 0, 0.85);
  color: #edf3ff;
  font-family: "Manrope", "Segoe UI", system-ui, sans-serif;
  font-size: 0.82rem;
  line-height: 1.45;
  text-align: center;
  transform: translate(-50%, 1rem);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.static-preview-toast.is-visible {
  opacity: 1;
  transform: translate(-50%, 0);
}

/* The role switcher and reset control need a live server, so hide them here. */
.viewas-bar {
  display: none !important;
}

@media (max-width: 720px) {
  .static-preview-bar {
    gap: 0.35rem 0.55rem;
    padding: 0.45rem 0.65rem;
    font-size: 0.68rem;
  }

  .static-preview-links a {
    padding: 0.14rem 0.4rem;
    font-size: 0.62rem;
  }
}
"""

PREVIEW_JS = """\
(function () {
  "use strict";

  var toast;

  function showNotice(message) {
    if (!toast) {
      toast = document.createElement("div");
      toast.className = "static-preview-toast";
      toast.setAttribute("role", "status");
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add("is-visible");
    window.clearTimeout(showNotice.timer);
    showNotice.timer = window.setTimeout(function () {
      toast.classList.remove("is-visible");
    }, 4200);
  }

  document.addEventListener(
    "submit",
    function (event) {
      var form = event.target;
      if (!(form instanceof HTMLFormElement)) return;
      if (form.closest(".static-preview-bar")) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      showNotice(
        "This is a read-only GitHub Pages preview. Sign-in, search filters and " +
          "donation actions work in the Flask app. See the README to run it locally."
      );
    },
    true
  );

  document.addEventListener(
    "click",
    function (event) {
      var link = event.target.closest("a[data-preview-missing]");
      if (!link) return;
      event.preventDefault();
      showNotice(
        "That page belongs to the signed-in workspace or a live action. " +
          "Run the Flask app locally to explore it."
      );
    },
    true
  );
})();
"""

ROLE_LABELS = {
    "public": "Public",
    "donor": "Donor",
    "recipient": "Recipient",
    "admin": "Admin",
}

ROLE_ORDER = ("public", "donor", "recipient", "admin")


def render_banner(root_prefix: str, workspace_prefix: str, current: str) -> str:
    links = []
    for role in ROLE_ORDER:
        if role == "public":
            href = f"{root_prefix}index.html"
        else:
            href = f"{workspace_prefix}{role}/index.html"
        active = ' class="is-current" aria-current="page"' if role == current else ""
        links.append(f'<a href="{href}"{active}>{ROLE_LABELS[role]}</a>')

    return (
        '<div class="static-preview-bar" role="note">'
        '<span class="static-preview-badge">Static preview</span>'
        f'<span class="static-preview-links">{"".join(links)}</span>'
        f'<a href="{REPO_URL}#quick-start" target="_blank" rel="noopener">Run locally &rarr;</a>'
        "</div>"
    )

ATTR_RE = re.compile(
    r'(?P<attr>\b(?:href|src|action|formaction|poster))=(?P<quote>["\'])(?P<url>.*?)(?P=quote)',
    re.IGNORECASE | re.DOTALL,
)
BODY_RE = re.compile(r"(<body\b[^>]*>)", re.IGNORECASE)
HEAD_RE = re.compile(r"(</head>)", re.IGNORECASE)
STATIC_URL_RE = re.compile(r"url\(\s*(['\"]?)/static/([^'\")]+)\1\s*\)", re.IGNORECASE)


def escape_attr(value: str) -> str:
    return html.escape(value, quote=True)


def inner_path(path: str) -> str:
    return path.rstrip("/") if path != "/" else path


def map_public_url(url: str, pages: dict[str, str], base: str) -> tuple[str, bool]:
    """Rewrite a public app URL to a relative static URL.

    Returns ``(url, missing)`` where ``missing`` marks links that exist only in
    the live Flask application.
    """
    if not url or url.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return url, False

    parts = urlsplit(url)
    if parts.scheme or parts.netloc:
        return url, False

    path = inner_path(parts.path)
    suffix = ("#" + parts.fragment) if parts.fragment else ""

    if path.startswith("/static/"):
        return base + "static/" + path[len("/static/") :] + suffix, False

    # Category views get their own pre-rendered page.
    if path == "/browse":
        category = (parse_qs(parts.query).get("category") or [""])[0]
        if category and f"browse-{category}.html" in pages.values():
            return base + f"browse-{category}.html" + suffix, False
        return base + "browse.html" + suffix, False

    if path in pages:
        return base + pages[path] + suffix, False

    listing = re.fullmatch(r"/listings/(\d+)", path)
    if listing:
        name = f"listing-{listing.group(1)}.html"
        if name in pages.values():
            return base + name + suffix, False

    member = re.fullmatch(r"/members/(\d+)", path)
    if member:
        name = f"member-{member.group(1)}.html"
        if name in pages.values():
            return base + name + suffix, False

    ad = re.fullmatch(r"/sponsored/(\d+)", path)
    if ad:
        name = f"sponsored-{ad.group(1)}.html"
        if name in pages.values():
            return base + name + suffix, False

    return "#", True


def rewrite_html(
    source: str,
    pages: dict[str, str],
    *,
    base: str = "",
    workspace_map: dict[str, str] | None = None,
    root_prefix: str = "",
    workspace_prefix: str = "workspace/",
    current: str = "public",
) -> str:
    def replace_attr(match: re.Match[str]) -> str:
        attr = match.group("attr")
        quote = match.group("quote")
        raw = html.unescape(match.group("url"))
        if not raw or raw.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            return match.group(0)

        parts = urlsplit(raw)
        if parts.scheme or parts.netloc:
            return match.group(0)

        path = inner_path(parts.path)
        suffix = ("#" + parts.fragment) if parts.fragment else ""

        if workspace_map and path in workspace_map:
            mapped = workspace_map[path] + suffix
            return f"{attr}={quote}{escape_attr(mapped)}{quote}"

        mapped, missing = map_public_url(raw, pages, base)
        extra = ' data-preview-missing=""' if missing else ""
        return f"{attr}={quote}{escape_attr(mapped)}{quote}{extra}"

    source = ATTR_RE.sub(replace_attr, source)
    source = STATIC_URL_RE.sub(
        lambda m: f"url('{base}static/{m.group(2)}')", source
    )

    # Add static-preview styling and behaviour.
    source = HEAD_RE.sub(
        f'<link rel="stylesheet" href="{root_prefix}static/css/preview.css">\\1',
        source,
        count=1,
    )
    source = BODY_RE.sub(
        lambda m: m.group(1) + render_banner(root_prefix, workspace_prefix, current),
        source,
        count=1,
    )
    source = source.replace(
        "</body>",
        f'<script src="{root_prefix}static/js/preview.js" defer></script>\n</body>',
    )
    return source


def write_page(
    name: str,
    source: str,
    pages: dict[str, str],
    **kwargs,
) -> None:
    target = DOCS / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rewrite_html(source, pages, **kwargs), encoding="utf-8")
    print(f"  {name}")


def ids(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[int]:
    return [row[0] for row in conn.execute(sql, params)]


WORKSPACE_ACCOUNTS = {
    "donor": "maya@antiimbak.com",
    "recipient": "josh@antiimbak.com",
    "admin": "admin@antiimbak.com",
}


def collect_workspace_pages(conn: sqlite3.Connection, role: str) -> list[tuple[str, str]]:
    """Return (app URL, static filename) pairs for a signed-in workspace."""
    row = conn.execute(
        "SELECT id FROM users WHERE email = ?", (WORKSPACE_ACCOUNTS[role],)
    ).fetchone()
    if row is None:
        return []
    user_id = row[0]

    if role == "donor":
        owned = ids(
            conn,
            "SELECT id FROM listings WHERE donor_id = ? AND status != 'removed' ORDER BY id",
            (user_id,),
        )
        claims = ids(
            conn,
            """SELECT DISTINCT id FROM claims
               WHERE claimant_id = ?
                  OR listing_id IN (SELECT id FROM listings WHERE donor_id = ?)
               ORDER BY id""",
            (user_id, user_id),
        )
        conversations = ids(
            conn,
            "SELECT id FROM conversations WHERE donor_id = ? OR recipient_id = ? ORDER BY id",
            (user_id, user_id),
        )
        planned = [
            ("/dashboard", "index.html"),
            ("/dashboard/donations", "donations.html"),
            ("/dashboard/donations/new", "new-donation.html"),
            ("/dashboard/claims", "incoming-claims.html"),
            ("/dashboard/claims/mine", "my-requests.html"),
            ("/dashboard/claimed", "claimed.html"),
            ("/dashboard/saved", "saved.html"),
            ("/dashboard/notifications", "notifications.html"),
            ("/dashboard/messages", "messages.html"),
            ("/dashboard/deliveries", "deliveries.html"),
            ("/dashboard/settings", "settings.html"),
            ("/dashboard/browse", "browse.html"),
        ]
        for listing_id in owned:
            planned.append(
                (f"/dashboard/donations/{listing_id}/edit", f"donation-{listing_id}-edit.html")
            )
            planned.append(
                (f"/dashboard/donations/{listing_id}/boost", f"donation-{listing_id}-boost.html")
            )
        for claim_id in claims:
            planned.append((f"/dashboard/claims/{claim_id}", f"claim-{claim_id}.html"))
        for conversation_id in conversations:
            planned.append(
                (f"/dashboard/messages/{conversation_id}", f"message-{conversation_id}.html")
            )
        return planned

    if role == "recipient":
        claims = ids(
            conn,
            "SELECT id FROM claims WHERE claimant_id = ? ORDER BY id",
            (user_id,),
        )
        conversations = ids(
            conn,
            "SELECT id FROM conversations WHERE donor_id = ? OR recipient_id = ? ORDER BY id",
            (user_id, user_id),
        )
        planned = [
            ("/dashboard", "index.html"),
            ("/dashboard/claims", "incoming-claims.html"),
            ("/dashboard/claims/mine", "my-requests.html"),
            ("/dashboard/claimed", "claimed.html"),
            ("/dashboard/saved", "saved.html"),
            ("/dashboard/notifications", "notifications.html"),
            ("/dashboard/messages", "messages.html"),
            ("/dashboard/deliveries", "deliveries.html"),
            ("/dashboard/settings", "settings.html"),
            ("/dashboard/browse", "browse.html"),
        ]
        for claim_id in claims:
            planned.append((f"/dashboard/claims/{claim_id}", f"claim-{claim_id}.html"))
        for conversation_id in conversations:
            planned.append(
                (f"/dashboard/messages/{conversation_id}", f"message-{conversation_id}.html")
            )
        return planned

    # Administrator
    members = ids(conn, "SELECT id FROM users ORDER BY id")
    disputes = ids(conn, "SELECT id FROM disputes ORDER BY id")
    concerns = ids(conn, "SELECT id FROM support_concerns ORDER BY id")
    planned = [
        ("/admin", "index.html"),
        ("/admin/users", "users.html"),
        ("/admin/listings", "listings.html"),
        ("/admin/reports", "reports.html"),
        ("/admin/disputes", "disputes.html"),
        ("/admin/support", "support.html"),
        ("/admin/activity", "activity.html"),
        ("/admin/revenue", "revenue.html"),
        ("/admin/content", "content.html"),
    ]
    for member_id in members:
        planned.append((f"/admin/users/{member_id}", f"user-{member_id}.html"))
    for dispute_id in disputes:
        planned.append((f"/admin/disputes/{dispute_id}", f"dispute-{dispute_id}.html"))
    for concern_id in concerns:
        planned.append((f"/admin/support/{concern_id}", f"concern-{concern_id}.html"))
    return planned


def main() -> int:
    if not SOURCE_DB.exists():
        print("No database found. Building the sample database first…")
        sys.path.insert(0, str(ROOT))
        import db

        db.init_db(force=True)

    if DOCS.exists():
        shutil.rmtree(DOCS)
    DOCS.mkdir(parents=True)

    with tempfile.TemporaryDirectory(prefix="antiimbak-pages-") as temp_dir:
        work_db = Path(temp_dir) / "antiimbak.db"
        shutil.copy2(SOURCE_DB, work_db)

        sys.path.insert(0, str(ROOT))
        import db
        import services

        # Render against a throwaway copy so page views and expirations do not
        # touch the developer's local database.
        db.DATABASE_PATH = work_db
        services.DATABASE_PATH = work_db

        import app as app_module

        app_module.DATABASE_PATH = work_db
        app = app_module.create_app()
        app.config.update(TESTING=True)
        client = app.test_client()

        with closing(sqlite3.connect(work_db)) as conn:
            listing_ids = [
                row[0]
                for row in conn.execute(
                    "SELECT id FROM listings WHERE status != 'removed' ORDER BY id"
                )
            ]
            user_ids = [row[0] for row in conn.execute("SELECT id FROM users ORDER BY id")]
            category_slugs = [
                row[0] for row in conn.execute("SELECT slug FROM categories ORDER BY sort_order")
            ]
            ad_ids = [
                row[0]
                for row in conn.execute(
                    "SELECT id FROM advertisements WHERE status = 'active' ORDER BY id"
                )
            ]

        pages = dict(STATIC_PAGES)
        for listing_id in listing_ids:
            pages[f"/listings/{listing_id}"] = f"listing-{listing_id}.html"
        for user_id in user_ids:
            pages[f"/members/{user_id}"] = f"member-{user_id}.html"
        for ad_id in ad_ids:
            pages[f"/sponsored/{ad_id}"] = f"sponsored-{ad_id}.html"
        for slug in category_slugs:
            pages[f"/browse?category={slug}"] = f"browse-{slug}.html"

        # Fetch every page before writing so links can be resolved up front.
        sources: dict[str, str] = {}
        failures: list[str] = []

        def fetch(url: str) -> None:
            response = client.get(url, follow_redirects=True)
            if response.status_code >= 400:
                failures.append(f"{url} -> {response.status_code}")
                return
            sources[url] = response.get_data(as_text=True)

        print("Rendering public pages…")
        for url in STATIC_PAGES:
            fetch(url)
        for slug in category_slugs:
            fetch(f"/browse?category={slug}")
        for listing_id in listing_ids:
            fetch(f"/listings/{listing_id}")
        for user_id in user_ids:
            fetch(f"/members/{user_id}")
        for ad_id in ad_ids:
            fetch(f"/sponsored/{ad_id}")

        not_found = client.get("/static-preview-not-found")
        if not_found.status_code == 404:
            sources["__not_found__"] = not_found.get_data(as_text=True)

        if failures:
            print("\nSome pages could not be rendered:")
            for failure in failures:
                print(f"  {failure}")
            return 1

        # Signed-in workspaces. Each role is rendered with a test-client session;
        # links to the other roles point at their exported snapshots.
        workspace_maps: dict[str, dict[str, str]] = {}
        workspace_sources: dict[str, dict[str, tuple[str, str]]] = {}
        warnings: list[str] = []

        print("Rendering signed-in workspaces…")
        for role in ("donor", "recipient", "admin"):
            with closing(sqlite3.connect(work_db)) as conn:
                planned = collect_workspace_pages(conn, role)
                user_row = conn.execute(
                    "SELECT id FROM users WHERE email = ?", (WORKSPACE_ACCOUNTS[role],)
                ).fetchone()
            if user_row is None:
                warnings.append(f"{role}: sample account is missing")
                continue

            with client.session_transaction() as session:
                session.clear()
                session["user_id"] = user_row[0]
                session.permanent = True

            rendered: dict[str, tuple[str, str]] = {}
            for url, filename in planned:
                response = client.get(url, follow_redirects=True)
                final_path = response.request.path
                if response.status_code != 200 or final_path.startswith("/auth/"):
                    warnings.append(
                        f"{role} {url} -> {response.status_code} {final_path}"
                    )
                    continue
                rendered[url] = (filename, response.get_data(as_text=True))

            with client.session_transaction() as session:
                session.clear()

            workspace_sources[role] = rendered
            workspace_maps[role] = {
                url: filename for url, (filename, _text) in rendered.items()
            }

        # Admin and recipient pages carry donor links (profile menu and the
        # donate button), so point those at the donor snapshot.
        donor_map = workspace_maps.get("donor", {})
        for role in ("recipient", "admin"):
            if role not in workspace_maps:
                continue
            alias = {
                url: f"../donor/{filename}"
                for url, filename in donor_map.items()
                if url not in workspace_maps[role]
            }
            workspace_maps[role].update(alias)

        # Copy the shared assets once, then the preview-only assets.
        shutil.copytree(
            STATIC_SRC,
            DOCS / "static",
            ignore=shutil.ignore_patterns("uploads"),
        )
        (DOCS / "static" / "css" / "preview.css").write_text(PREVIEW_CSS, encoding="utf-8")
        (DOCS / "static" / "js" / "preview.js").write_text(PREVIEW_JS, encoding="utf-8")

        print("Writing static pages…")
        for url, name in STATIC_PAGES.items():
            write_page(name, sources[url], pages)
        for slug in category_slugs:
            write_page(f"browse-{slug}.html", sources[f"/browse?category={slug}"], pages)
        for listing_id in listing_ids:
            write_page(f"listing-{listing_id}.html", sources[f"/listings/{listing_id}"], pages)
        for user_id in user_ids:
            write_page(f"member-{user_id}.html", sources[f"/members/{user_id}"], pages)
        for ad_id in ad_ids:
            write_page(f"sponsored-{ad_id}.html", sources[f"/sponsored/{ad_id}"], pages)
        if "__not_found__" in sources:
            write_page("404.html", sources["__not_found__"], pages)

        print("Writing signed-in workspaces…")
        for role, rendered in workspace_sources.items():
            role_map = workspace_maps[role]
            for url, (filename, source) in rendered.items():
                write_page(
                    f"workspace/{role}/{filename}",
                    source,
                    pages,
                    base="../../",
                    workspace_map=role_map,
                    root_prefix="../../",
                    workspace_prefix="../",
                    current=role,
                )

        if warnings:
            print("\nSkipped workspace pages (not available for that sample account):")
            for warning in warnings:
                print(f"  {warning}")

    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    (DOCS / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n", encoding="utf-8"
    )
    total = len(list(DOCS.rglob("*.html")))
    print(f"\nBuilt {total} pages into {DOCS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
