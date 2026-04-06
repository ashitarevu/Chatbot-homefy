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
    print(f"\n🏠  Homefy Chatbot running at http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=debug)
