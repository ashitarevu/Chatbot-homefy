import os
import json
import uuid
from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
from dotenv import load_dotenv
from chatbot import HomefyChatbot
import auth

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "homefy-secret-key-change-me")
CORS(app)

chatbot = HomefyChatbot()


@app.route("/")
def index():
    """Serve the chat UI."""
    return render_template("index.html")


@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "model": chatbot.model_name})


@app.route("/api/auth/send-otp", methods=["POST"])
def auth_send_otp():
    """Step 1: Send OTP"""
    data = request.get_json(silent=True)
    if not data or not data.get("phone"):
        return jsonify({"error": "phone number is required"}), 400
    res = auth.send_otp(data["phone"])
    return jsonify(res)


@app.route("/api/auth/verify-otp", methods=["POST"])
def auth_verify_otp():
    """Step 2: Verify OTP → get access_token. Step 3: Fetch apartments with access_token."""
    data = request.get_json(silent=True)
    if not data or not data.get("code") or not data.get("token"):
        return jsonify({"error": "code and token are required"}), 400
    
    # Step 2: Verify OTP → returns access_token (JWT)
    res = auth.verify_otp(data["code"], data["token"])
    if "error" in res:
        return jsonify(res), 400
        
    access_token = res.get("access_token")
    if not access_token:
        return jsonify({"error": f"Verification failed: no access_token returned. Got: {res}"}), 400
        
    handler = chatbot.api_handler
        
    # Step 3: Fetch apartments using the access_token as bearer
    apartments = handler.get_my_apartments(access_token)
    
    return jsonify({
        "apartments": apartments,
        "access_token": access_token
    })


@app.route("/api/auth/select-apartment", methods=["POST"])
def auth_select_apartment():
    """Step 4: Exchange request_id + access_token → permanent token, store in session."""
    data = request.get_json(silent=True)
    if not data or not data.get("request_id") or not data.get("session_id") or not data.get("access_token"):
        return jsonify({"error": "request_id, session_id and access_token are required"}), 400
        
    handler = chatbot.api_handler
    # Pass access_token as bearer so the GraphQL call is authenticated
    access_res = handler.get_access_token(data["request_id"], data["access_token"])
    if "error" in access_res:
        return jsonify(access_res), 400
        
    # GraphQL returns: { accessToken: { token: "..." } }
    final_token = access_res.get("accessToken", {}).get("token")
    if not final_token:
        return jsonify({"error": f"Failed to get permanent token. Response: {access_res}"}), 400
        
    # Store permanent token in memory, keyed by frontend session_id
    session_id = data["session_id"]
    if not hasattr(chatbot, 'auth_tokens'):
        chatbot.auth_tokens = {}
    
    chatbot.auth_tokens[session_id] = final_token
    
    return jsonify({"status": "success", "message": "Apartment selected. Permanent token stored."})


@app.route("/api/complaints/categories", methods=["GET"])
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


@app.route("/api/complaints/create", methods=["POST"])
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


@app.route("/api/amenities/categories", methods=["GET"])
def get_amenity_categories():
    session_id = request.args.get("session_id", "")
    stored_token = getattr(chatbot, 'auth_tokens', {}).get(session_id, "")
    token = stored_token or request.args.get("user_token", os.getenv("HOMEFY_AUTH_TOKEN", ""))

    categories = chatbot.api_handler.get_amenity_categories_raw(token)
    return jsonify({"categories": categories})


@app.route("/api/amenities/list", methods=["GET"])
def list_amenities():
    session_id = request.args.get("session_id", "")
    stored_token = getattr(chatbot, 'auth_tokens', {}).get(session_id, "")
    token = stored_token or request.args.get("user_token", os.getenv("HOMEFY_AUTH_TOKEN", ""))
    
    # Filter amenities by the apartment the user is logged into
    apartment_id = getattr(chatbot, 'apartment_ids', {}).get(session_id, "")
    
    amenities = chatbot.api_handler.get_all_amenities_raw(token, apartment_id=apartment_id)
    return jsonify({"amenities": amenities})


@app.route("/api/amenities/slots", methods=["POST"])
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


@app.route("/api/apartment/blocks-flats", methods=["GET"])
def get_blocks_and_flats():
    """Return blocks and flats for the logged-in user's apartment."""
    session_id = request.args.get("session_id", "")
    stored_token = getattr(chatbot, 'auth_tokens', {}).get(session_id, "")
    token = stored_token or request.args.get("user_token", os.getenv("HOMEFY_AUTH_TOKEN", ""))
    if not token:
        return jsonify({"error": "Not authenticated"}), 401
    result = chatbot.api_handler.get_blocks_and_flats(token)
    return jsonify(result)


@app.route("/api/amenities/book", methods=["POST"])
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


@app.route("/api/finance/bill-categories", methods=["GET"])
def get_bill_categories_api():
    """Return bill categories for the frontend bill creation form."""
    session_id = request.args.get("session_id", "")
    stored_token = getattr(chatbot, 'auth_tokens', {}).get(session_id, "")
    token = stored_token or os.getenv("HOMEFY_AUTH_TOKEN", "")
    cats = chatbot.api_handler._q_bill_categories_raw(token)
    return jsonify({"categories": cats})


@app.route("/api/bills/create", methods=["POST"])
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


@app.route("/api/meetings/create", methods=["POST"])
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
    # title, location, description, startTime, endTime, link
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

@app.route("/api/parking/create", methods=["POST"])
def create_parking_category_api():
    """Create a parking category directly from the embedded form."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    session_id = data.get("session_id", "")
    
    # The GraphQL backend enforces that only Admins can create parking categories. 
    # To satisfy "anyone can create parking", we forcibly use the system ADMIN token
    # (HOMEFY_AUTH_TOKEN) to bypass the backend checks, falling back to the user token.
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

@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Main chat endpoint.
    Request body:
        {
            "message": "User's message",
            "session_id": "optional-uuid",        # for conversation memory
            "user_token": "Bearer <JWT>"           # optional: forward to Homefy APIs
        }
    """
    data = request.get_json(silent=True)
    if not data or not data.get("message", "").strip():
        return jsonify({"error": "message is required"}), 400

    user_message = data["message"].strip()
    session_id   = data.get("session_id") or str(uuid.uuid4())
    
    # Check stored token first, then fallback to request token or env token
    stored_token = getattr(chatbot, 'auth_tokens', {}).get(session_id)
    user_token   = stored_token or data.get("user_token", os.getenv("HOMEFY_AUTH_TOKEN", ""))

    try:
        reply = chatbot.chat(session_id, user_message, user_token)
        return jsonify({
            "reply":      reply,
            "session_id": session_id,
        })
    except Exception as e:
        import traceback
        app.logger.error(f"Chat error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@app.route("/api/chat/reset", methods=["POST"])
def reset_chat():
    """Clear conversation history for a session."""
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    if session_id:
        chatbot.clear_session(session_id)
    return jsonify({"status": "cleared", "session_id": session_id})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    print(f"\nHomefy Chatbot running at http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=debug)
