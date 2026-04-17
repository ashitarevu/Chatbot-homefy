import os
from dotenv import load_dotenv

# Load env variables before doing anything else
load_dotenv()

# Instantiate the shared global chatbot object so blueprints can import it from here
from app.services.chatbot_service import HomefyChatbot
chatbot_instance = HomefyChatbot()
