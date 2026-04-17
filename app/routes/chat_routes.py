import os
import uuid
import traceback
from flask import Blueprint, request, jsonify, current_app
from app.services.bot_instance import chatbot_instance as chatbot

chat_bp = Blueprint('chat', __name__, url_prefix='/api/chat')

@chat_bp.route("", methods=["POST"])
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
        current_app.logger.error(f"Chat error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@chat_bp.route("/reset", methods=["POST"])
def reset_chat():
    """Clear conversation history for a session."""
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    if session_id:
        chatbot.clear_session(session_id)
    return jsonify({"status": "cleared", "session_id": session_id})
