import os
from flask import Blueprint, request, jsonify
from app.services.bot_instance import chatbot_instance as chatbot

finance_bp = Blueprint('finance', __name__, url_prefix='/api')

@finance_bp.route("/finance/bill-categories", methods=["GET"])
def get_bill_categories_api():
    """Return bill categories for the frontend bill creation form."""
    session_id = request.args.get("session_id", "")
    stored_token = getattr(chatbot, 'auth_tokens', {}).get(session_id, "")
    token = stored_token or os.getenv("HOMEFY_AUTH_TOKEN", "")
    cats = chatbot.api_handler._q_bill_categories_raw(token)
    return jsonify({"categories": cats})


@finance_bp.route("/bills/create", methods=["POST"])
def create_bill_api():
    """Create a bill directly from the embedded form."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    session_id = data.get("session_id", "")
    stored_token = getattr(chatbot, 'auth_tokens', {}).get(session_id, "")
    token = stored_token or data.get("user_token", os.getenv("HOMEFY_AUTH_TOKEN", ""))

    if not token:
        return jsonify({"error": "You must be logged in to create a bill."}), 401

    required = ["amount", "category_id", "flat_id", "last_date", "applicable_to"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    # Ensure last_date is ISO8601 string if not already
    last_dt = data["last_date"]
    if "T" not in last_dt:
        last_dt += "T00:00:00.000Z"
        
    result = chatbot.api_handler.create_bill(
        token=token,
        amount=data["amount"],
        category_id=data["category_id"],
        flat_id=data["flat_id"],
        last_date=last_dt,
        applicable_to=data["applicable_to"],
        notes=data.get("notes", "")
    )

    if result.get("status") == "error":
        return jsonify(result), 500
    return jsonify(result)
