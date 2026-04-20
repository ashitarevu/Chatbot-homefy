from flask import Blueprint, request, jsonify
from app.services.bot_instance import chatbot_instance as chatbot

announcement_bp = Blueprint('announcement_bp', __name__)

@announcement_bp.route('/api/announcements/categories', methods=['GET'])
def get_announcement_categories():
    session_id = request.args.get('session_id', 'default')
    token = chatbot.auth_tokens.get(session_id)
    if not token:
        return jsonify({"error": "Unauthorized"}), 401
    
    categories = chatbot.api_handler._q_get_announcement_categories(token)
    return jsonify({"categories": categories})

@announcement_bp.route('/api/announcements/create', methods=['POST'])
def create_announcement():
    data = request.json
    session_id = data.get('session_id', 'default')
    token = chatbot.auth_tokens.get(session_id)
    if not token:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    res = chatbot.api_handler.add_announcement(
        token=token,
        title=data.get('title'),
        description=data.get('description'),
        category_id=data.get('category_id'),
        ann_type=data.get('type', 'ALL')
    )
    return jsonify(res)
