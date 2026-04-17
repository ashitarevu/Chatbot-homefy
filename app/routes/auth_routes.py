from flask import Blueprint, request, jsonify
from app.services.bot_instance import chatbot_instance as chatbot
from app.services import auth_service as auth

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

@auth_bp.route("/send-otp", methods=["POST"])
def auth_send_otp():
    """Step 1: Send OTP"""
    data = request.get_json(silent=True)
    if not data or not data.get("phone"):
        return jsonify({"error": "phone number is required"}), 400
    res = auth.send_otp(data["phone"])
    return jsonify(res)


@auth_bp.route("/verify-otp", methods=["POST"])
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


@auth_bp.route("/select-apartment", methods=["POST"])
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
