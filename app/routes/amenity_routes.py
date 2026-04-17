import os
from flask import Blueprint, request, jsonify
from app.services.bot_instance import chatbot_instance as chatbot

amenity_bp = Blueprint('amenity', __name__, url_prefix='/api')

@amenity_bp.route("/amenities/categories", methods=["GET"])
def get_amenity_categories():
    session_id = request.args.get("session_id", "")
    stored_token = getattr(chatbot, 'auth_tokens', {}).get(session_id, "")
    token = stored_token or request.args.get("user_token", os.getenv("HOMEFY_AUTH_TOKEN", ""))

    categories = chatbot.api_handler.get_amenity_categories_raw(token)
    return jsonify({"categories": categories})

@amenity_bp.route("/amenities/list", methods=["GET"])
def list_amenities():
    session_id = request.args.get("session_id", "")
    stored_token = getattr(chatbot, 'auth_tokens', {}).get(session_id, "")
    token = stored_token or request.args.get("user_token", os.getenv("HOMEFY_AUTH_TOKEN", ""))
    
    # Filter amenities by the apartment the user is logged into
    apartment_id = getattr(chatbot, 'apartment_ids', {}).get(session_id, "")
    
    amenities = chatbot.api_handler.get_all_amenities_raw(token, apartment_id=apartment_id)
    return jsonify({"amenities": amenities})

@amenity_bp.route("/amenities/slots", methods=["POST"])
def get_amenity_slots():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body is required"}), 400
        
    session_id = data.get("session_id", "")
    stored_token = getattr(chatbot, 'auth_tokens', {}).get(session_id, "")
    token = stored_token or data.get("user_token", os.getenv("HOMEFY_AUTH_TOKEN", ""))
    
    required = ["amenity_id", "start_date", "end_date"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400
        
    result = chatbot.api_handler.get_amenity_slots(token, data["amenity_id"], data["start_date"], data["end_date"])
    
    if result.get("status") == "error":
        return jsonify(result), 500
    return jsonify(result)

@amenity_bp.route("/apartment/blocks-flats", methods=["GET"])
def get_blocks_and_flats():
    """Return blocks and flats for the logged-in user's apartment."""
    session_id = request.args.get("session_id", "")
    stored_token = getattr(chatbot, 'auth_tokens', {}).get(session_id, "")
    token = stored_token or request.args.get("user_token", os.getenv("HOMEFY_AUTH_TOKEN", ""))
    if not token:
        return jsonify({"error": "Not authenticated"}), 401
    result = chatbot.api_handler.get_blocks_and_flats(token)
    return jsonify(result)

@amenity_bp.route("/amenities/book", methods=["POST"])
def book_amenity():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body is required"}), 400
        
    session_id = data.get("session_id", "")
    stored_token = getattr(chatbot, 'auth_tokens', {}).get(session_id, "")
    token = stored_token or data.get("user_token", os.getenv("HOMEFY_AUTH_TOKEN", ""))
    
    if not token:
        return jsonify({"error": "You must be logged in to book an amenity."}), 401
        
    required = ["amenity_id", "slot_ids"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400
        
    flat_id = data.get("flat_id", "")
    
    result = chatbot.api_handler.create_amenity_booking(token, data["amenity_id"], data["slot_ids"], flat_id)
    
    if result.get("status") == "error":
        return jsonify(result), 500
    return jsonify(result)
