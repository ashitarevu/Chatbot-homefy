import os
from flask import Blueprint, request, jsonify
from app.services.bot_instance import chatbot_instance as chatbot

complaint_bp = Blueprint('complaint', __name__, url_prefix='/api/complaints')

@complaint_bp.route("/categories", methods=["GET"])
def get_complaint_categories():
    """Return complaint categories for the form dropdown."""
    session_id = request.args.get("session_id", "")
    stored_token = getattr(chatbot, 'auth_tokens', {}).get(session_id, "")
    token = stored_token or os.getenv("HOMEFY_AUTH_TOKEN", "")
    
    try:
        cats = chatbot.api_handler._q_get_categories(token)
        return jsonify({"categories": cats})
    except Exception:
        return jsonify({"categories": chatbot.api_handler.FALLBACK_CATEGORIES})


@complaint_bp.route("/create", methods=["POST"])
def create_complaint_direct():
    """Create a complaint directly from the embedded form (bypasses LLM)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    session_id = data.get("session_id", "")
    stored_token = getattr(chatbot, 'auth_tokens', {}).get(session_id, "")
    token = stored_token or data.get("user_token", os.getenv("HOMEFY_AUTH_TOKEN", ""))

    if not token:
        return jsonify({"error": "You must be logged in to raise a complaint."}), 401

    required = ["category_id", "type", "description"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    # Build a short title from the description (max 40 chars as per API)
    desc = data["description"].strip()
    title = desc[:35] + ("..." if len(desc) > 35 else "")

    result = chatbot.api_handler.create_complaint(
        token=token,
        title=title,
        description=desc,
        category_id=data["category_id"],
        type_filter=data["type"],
        location=data.get("location", ""),
        is_urgent=data.get("is_urgent", False)
    )

    if result.get("status") == "error":
        return jsonify(result), 500
    return jsonify(result)
