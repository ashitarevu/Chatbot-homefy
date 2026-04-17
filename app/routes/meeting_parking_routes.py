import os
from flask import Blueprint, request, jsonify
from app.services.bot_instance import chatbot_instance as chatbot

meeting_parking_bp = Blueprint('meeting_parking', __name__, url_prefix='/api')

@meeting_parking_bp.route("/meetings/create", methods=["POST"])
def create_meeting_api():
    """Create a meeting directly from the embedded form."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    session_id = data.get("session_id", "")
    stored_token = getattr(chatbot, 'auth_tokens', {}).get(session_id, "")
    token = stored_token or data.get("user_token", os.getenv("HOMEFY_AUTH_TOKEN", ""))

    if not token:
        return jsonify({"error": "You must be logged in to schedule a meeting."}), 401

    required = ["title", "location", "startTime", "endTime"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    # The data dict should match the CreateMeetingInput schema:
    gql_data = {
        "title": data.get("title"),
        "location": data.get("location"),
        "startTime": data.get("startTime"),
        "endTime": data.get("endTime"),
        "description": data.get("description", ""),
        "link": data.get("link", "")
    }
    
    apartment_id = getattr(chatbot, 'apartment_ids', {}).get(session_id, "")
    result = chatbot.api_handler.create_meeting(token, gql_data, apartment_id=apartment_id)

    if result.get("status") == "error":
        return jsonify(result), 500
    return jsonify(result)


@meeting_parking_bp.route("/parking/create", methods=["POST"])
def create_parking_category_api():
    """Create a parking category directly from the embedded form."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    session_id = data.get("session_id", "")
    
    token = os.getenv("HOMEFY_AUTH_TOKEN")
    if not token:
        stored_token = getattr(chatbot, 'auth_tokens', {}).get(session_id, "")
        token = stored_token or data.get("user_token", "")

    if not token:
        return jsonify({"error": "You must be logged in to create a parking category."}), 401

    required = ["name", "p_type", "min_booking", "payment_type"]
    missing = [f for f in required if data.get(f) is None or str(data.get(f)) == ""]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    apartment_id = getattr(chatbot, 'apartment_ids', {}).get(session_id, "")

    result = chatbot.api_handler.create_parking_category(
        token=token,
        name=data.get("name"),
        p_type=data.get("p_type"),
        min_booking=data.get("min_booking"),
        schedule_type="DAY",
        payment_type=data.get("payment_type"),
        base_price=data.get("base_price", 0),
        max_booking=data.get("max_booking"),
        apartment_id=apartment_id
    )

    if result.get("status") == "error":
        return jsonify(result), 500
    return jsonify(result)
