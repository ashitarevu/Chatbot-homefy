import os
import importlib

from flask import Flask
from flask_cors import CORS

def create_app():
    """Application factory function."""
    
    # Adjust paths so templates/static are picked up from the root folder
    app = Flask(__name__, 
                template_folder='../templates', 
                static_folder='../static')
                
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "homefy-secret-key-change-me")
    CORS(app)
    
    # Register Blueprints
    from app.routes import (
        auth_bp, complaint_bp, amenity_bp, finance_bp,
        meeting_parking_bp, chat_bp, view_bp
    )
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(complaint_bp)
    app.register_blueprint(amenity_bp)
    app.register_blueprint(finance_bp)
    app.register_blueprint(meeting_parking_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(view_bp)
    
    return app
