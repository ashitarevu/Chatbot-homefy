from chatbot import HomefyChatbot
import json

bot = HomefyChatbot()
res = bot._detect_intent("show all amenities")
print("INTENT:", res)

ctx = bot.api_handler.call_apis_in_sequence("amenities", "")
print("CONTEXT:", ctx)
