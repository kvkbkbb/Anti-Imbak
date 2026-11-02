"""Small JSON endpoints used by the progressive-enhancement interface."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from services import delivery_quote, get_listing_detail, login_required

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.route("/delivery-quote")
@login_required
def quote():
    listing_id = request.args.get("listing_id", type=int)
    if not listing_id:
        return jsonify({"ok": False, "message": "Choose a listing first."}), 400
    listing = get_listing_detail(listing_id)
    if listing is None:
        return jsonify({"ok": False, "message": "Listing not found."}), 404
    quote_data = delivery_quote(listing, g.get("user"))
    return jsonify(
        {
            "ok": True,
            "method_label": "Partnered Delivery",
            "distance_km": quote_data["distance_km"],
            "fee": quote_data["fee"],
            "fee_display": f"₱{quote_data['fee']:,.2f}",
            "fee_min_display": f"₱{quote_data['fee_min']:,.0f}",
            "fee_max_display": f"₱{quote_data['fee_max']:,.0f}",
            "partner_name": quote_data["partner_name"],
            "service_type": quote_data["service_type"],
            "eta": quote_data["eta"],
            "message": "Inclusive delivery fee. No additional charges.",
        }
    )
