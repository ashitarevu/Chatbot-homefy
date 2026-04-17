import os
from flask import Blueprint, render_template, jsonify
from app.services.bot_instance import chatbot_instance as chatbot

view_bp = Blueprint('view_routes', __name__)

@view_bp.route("/")
def index():
    """Serve the chat UI."""
    return render_template("index.html")

@view_bp.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "model": chatbot.model_name})
